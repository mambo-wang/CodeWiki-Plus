"""Tests for the `sync-skills` CLI command (ADR-0019)."""

import click
import pytest
from click.testing import CliRunner

from codewiki.cli.commands.sync_skills import (
    _STATIC_SKILL_NAMES,
    _default_arguments,
    _host_skills_dir,
    _prune_stale_skills,
    _render_all,
    _render_skill,
    _resolve_targets,
    sync_skills,
)
from codewiki.mcp import i18n
from codewiki.mcp.prompts import _PROMPT_REGISTRY
from codewiki.src.skill_match import parse_skill_frontmatter

# 渲染集合 = registry 编译产物 + 静态资产（codewiki-setup）
COUNT = len(_PROMPT_REGISTRY) + len(_STATIC_SKILL_NAMES)


@pytest.fixture(autouse=True)
def _fix_lang(monkeypatch):
    """固定语言：屏蔽 init_lang 的环境重读，测试用 set_lang 显式控制。"""
    monkeypatch.setattr(i18n, "init_lang", lambda: None)
    yield
    i18n.set_lang("zh")


def _meta_of(name: str) -> dict:
    return next(m for m in _PROMPT_REGISTRY if m["name"] == name)


def _render(name: str, lang: str = "zh") -> str:
    """按 CLI 同款顺序渲染单个技能（先全局定语言，再渲染）。"""
    i18n.set_lang(lang)
    title = i18n.t(f"prompts.{name}.title")
    description = i18n.t(f"prompts.{name}.description")
    return _render_skill(name, title, description, lang)


# ---------------------------------------------------------------------------
# 渲染：全量覆盖 registry
# ---------------------------------------------------------------------------


def test_render_all_covers_registry():
    rendered = _render_all("zh")
    assert len(rendered) == COUNT
    names = {name for _, name, _ in rendered}
    assert names == {meta["name"] for meta in _PROMPT_REGISTRY} | set(_STATIC_SKILL_NAMES)


def test_render_all_dir_names_carry_prefix():
    rendered = _render_all("zh")
    dir_names = {dir_name for dir_name, _, _ in rendered}
    assert dir_names == {f"codewiki-{meta['name']}" for meta in _PROMPT_REGISTRY} | set(
        _STATIC_SKILL_NAMES
    )


# ---------------------------------------------------------------------------
# 静态资产：codewiki-setup（随包分发，可原样发布 skillhub）
# ---------------------------------------------------------------------------


def test_static_setup_skill_in_render_set():
    rendered = _render_all("zh")
    by_dir = {dir_name: content for dir_name, _, content in rendered}
    assert "codewiki-setup" in by_dir
    content = by_dir["codewiki-setup"]
    assert content.startswith("---\nname: codewiki-setup\n")
    assert "disable-model-invocation: true" in content
    assert "pip install --upgrade codewiki-plus" in content
    assert "codewiki setup" in content


def test_static_setup_skill_en_no_chinese_residue():
    rendered = _render_all("en")
    by_dir = {dir_name: content for dir_name, _, content in rendered}
    content = by_dir["codewiki-setup"]
    assert "pip install --upgrade codewiki-plus" in content
    assert "一键" not in content
    assert "安装/升级包" not in content
    fm = parse_skill_frontmatter(content)
    assert fm["name"] == "codewiki-setup"
    assert fm["disable-model-invocation"] == "true"


# ---------------------------------------------------------------------------
# 命名：目录名恒 codewiki-<kebab-name>，不随 locale 变化（ADR-0019 决策 3）
# ---------------------------------------------------------------------------


def test_skill_dir_name_locale_invariant():
    i18n.set_lang("zh")
    zh_dirs = {dir_name for dir_name, _, _ in _render_all("zh")}
    i18n.set_lang("en")
    en_dirs = {dir_name for dir_name, _, _ in _render_all("en")}
    assert zh_dirs == en_dirs
    assert "codewiki-init-wiki" in zh_dirs


# ---------------------------------------------------------------------------
# arguments 注入（对齐手写薄壳）
# ---------------------------------------------------------------------------


def test_arguments_path_args_dot():
    assert _default_arguments(_meta_of("init-wiki")) == '{"repo_path": "."}'
    assert _default_arguments(_meta_of("init-workspace")) == '{"workspace_path": "."}'
    assert _default_arguments(_meta_of("generate-wiki")) == '{"repo_path": "."}'


def test_arguments_required_placeholder():
    assert (
        _default_arguments(_meta_of("add-workspace-repo"))
        == '{"workspace_path": ".", "url": "<url>"}'
    )
    assert _default_arguments(_meta_of("search-wiki")) == '{"query": "<query>"}'
    assert (
        _default_arguments(_meta_of("extract-knowledge"))
        == '{"source_path": "<source_path>", "repo_path": ".", "granularity": "<granularity>"}'
    )


def test_arguments_switch_skipped():
    args = _default_arguments(_meta_of("init-wiki"))
    assert "enable_task_management" not in args
    assert "capture" not in args
    assert "clone" not in _default_arguments(_meta_of("add-workspace-repo"))


# ---------------------------------------------------------------------------
# 薄壳内容：frontmatter 三行 + 指向 get_prompt，不渲染全文
# ---------------------------------------------------------------------------


def test_skill_frontmatter_three_lines():
    content = _render("init-wiki")
    assert content.startswith('---\nname: codewiki-init-wiki\ndescription: "')
    assert "\ndisable-model-invocation: true\n---\n" in content
    # 字段顺序固定：name → description → disable-model-invocation（对齐 grill-me 先例）
    head = content.split("---\n", 2)[1]
    keys = [line.split(":", 1)[0] for line in head.splitlines() if line.strip()]
    assert keys == ["name", "description", "disable-model-invocation"]


def test_skill_points_to_get_prompt():
    content = _render("init-wiki")
    assert "\n# 初始化单仓Wiki工作区\n" in content
    assert 'get_prompt(name="init-wiki", arguments={"repo_path": "."})' in content
    assert "以 `get_prompt` 返回内容为准" in content
    assert "/codewiki-init-wiki" in content


def test_skill_description_double_quoted():
    # en 文案含 `": "`，裸写非法 YAML——description 必须双引号包裹
    content = _render("init-wiki", "en")
    head = content.split("---\n", 2)[1]
    desc_line = next(line for line in head.splitlines() if line.startswith("description:"))
    value = desc_line.partition(":")[2].strip()
    assert value.startswith('"') and value.endswith('"')


# ---------------------------------------------------------------------------
# 中英双态：整文件语言跟随 --lang（用户要求，ADR-0019 决策 2）
# ---------------------------------------------------------------------------


def test_en_render_body_is_english():
    content = _render("init-wiki", "en")
    assert "Call MCP to fetch the full workflow" in content
    assert "Do not run from memory" in content
    assert "manual entry point" in content
    # en 产物不得残留中文样板段落
    assert "调用 MCP 获取完整工作流" not in content
    assert "不要凭记忆执行" not in content
    assert "可选开关参数" not in content


def test_en_render_switch_hints_are_english():
    content = _render("init-wiki", "en")
    assert "Optional switches" in content
    assert 'pass "false" only when the user explicitly declines' in content
    assert "默认启用任务管理接线" not in content


def test_zh_render_body_is_chinese():
    content = _render("init-wiki", "zh")
    assert "调用 MCP 获取完整工作流并按其执行" in content
    assert "可选开关参数" in content
    assert "Call MCP to fetch the full workflow" not in content


# ---------------------------------------------------------------------------
# 开关参数映射指引：用户意愿须结构化进 arguments（2026-09-29 事故修复）
# ---------------------------------------------------------------------------


def test_skill_switch_block_lists_enable_task_management():
    content = _render("init-wiki")
    assert "enable_task_management" in content
    assert '传 "false"' in content
    assert "不要丢弃" in content


def test_skill_switch_block_lists_capture_and_clone():
    content = _render("init-workspace")
    assert "capture" in content
    content = _render("add-workspace-repo")
    assert "clone" in content


def test_skill_no_switch_block_for_plain_prompts():
    content = _render("search-wiki")
    assert "可选开关参数" not in content
    assert "Optional switches" not in content


# ---------------------------------------------------------------------------
# 宿主判定（ADR-0019 决策 4）：codebuddy 不再豁免
# ---------------------------------------------------------------------------


def test_resolve_targets_explicit_ide(tmp_path):
    assert _resolve_targets(str(tmp_path), "qoder") == ["qoder"]
    # codebuddy 是合法显式目标（IDE 只自动映射 prompt→command，无 prompt→skill 通道）
    assert _resolve_targets(str(tmp_path), "codebuddy") == ["codebuddy"]
    with pytest.raises(click.UsageError):
        _resolve_targets(str(tmp_path), "unknown-ide")
    with pytest.raises(click.UsageError):
        _resolve_targets(str(tmp_path), "qwenwork")  # 无仓库配置目录


def test_resolve_targets_detect_includes_codebuddy(tmp_path):
    (tmp_path / ".codebuddy").mkdir()
    (tmp_path / ".qoder").mkdir()
    assert _resolve_targets(str(tmp_path), None) == ["codebuddy", "qoder"]


def test_resolve_targets_fallback_trae(tmp_path):
    # 无任何 IDE 目录 -> 兜底 .trae 登记处（主动创建）
    assert _resolve_targets(str(tmp_path), None) == ["trae"]


def test_sync_creates_trae_fallback(tmp_path):
    i18n.set_lang("zh")
    runner = CliRunner()
    result = runner.invoke(sync_skills, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    target = tmp_path / ".trae" / "skills"
    assert target.is_dir()
    assert (target / "codewiki-init-wiki" / "SKILL.md").exists()
    assert len([d for d in target.iterdir() if d.is_dir()]) == COUNT


def test_host_skills_dir(tmp_path):
    assert _host_skills_dir(str(tmp_path), "qoder") == (tmp_path / ".qoder" / "skills")
    assert _host_skills_dir(str(tmp_path), "codebuddy") == (tmp_path / ".codebuddy" / "skills")
    with pytest.raises(click.UsageError):
        _host_skills_dir(str(tmp_path), "qwenwork")  # 无仓库配置目录


# ---------------------------------------------------------------------------
# 写盘：全量覆盖 + 幂等
# ---------------------------------------------------------------------------


def test_sync_writes_and_is_idempotent(tmp_path):
    i18n.set_lang("zh")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_skills, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    target = tmp_path / ".qoder" / "skills"
    assert (target / "codewiki-init-wiki" / "SKILL.md").exists()
    assert len([d for d in target.iterdir() if d.is_dir()]) == COUNT
    # 幂等重跑（全量覆盖，不报错、不翻倍）
    assert runner.invoke(sync_skills, [str(tmp_path)]).exit_code == 0
    assert len([d for d in target.iterdir() if d.is_dir()]) == COUNT


def test_sync_dry_run_no_write(tmp_path):
    i18n.set_lang("zh")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_skills, ["--dry-run", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert not (tmp_path / ".qoder" / "skills").exists()


def test_sync_en_lang_writes_english_content(tmp_path):
    i18n.set_lang("en")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_skills, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    skill = tmp_path / ".qoder" / "skills" / "codewiki-init-wiki" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    assert "Call MCP to fetch the full workflow" in text
    assert "调用 MCP 获取完整工作流" not in text


# ---------------------------------------------------------------------------
# prune：快照口径——不在渲染集合内的 codewiki-* 目录删除，他人技能不动
# ---------------------------------------------------------------------------


def test_sync_prunes_stale_codewiki_skills(tmp_path):
    i18n.set_lang("zh")
    skills_dir = tmp_path / ".qoder" / "skills"
    (skills_dir / "codewiki-obsolete").mkdir(parents=True)
    (skills_dir / "codewiki-obsolete" / "SKILL.md").write_text("stale", encoding="utf-8")
    (skills_dir / "other-skill").mkdir()
    (skills_dir / "other-skill" / "SKILL.md").write_text("mine", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(sync_skills, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert not (skills_dir / "codewiki-obsolete").exists()
    assert (skills_dir / "other-skill" / "SKILL.md").read_text(encoding="utf-8") == "mine"


def test_prune_dry_run_previews_only(tmp_path):
    skills_dir = tmp_path / ".qoder" / "skills"
    (skills_dir / "codewiki-obsolete").mkdir(parents=True)
    pruned = _prune_stale_skills(skills_dir, keep=set(), dry_run=True)
    assert pruned == ["codewiki-obsolete"]
    assert (skills_dir / "codewiki-obsolete").exists()


def test_prune_ignores_missing_dir(tmp_path):
    assert _prune_stale_skills(tmp_path / "nope", keep=set(), dry_run=False) == []


def test_prune_skips_symlinked_dirs(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    link = skills_dir / "codewiki-stale"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不支持创建符号链接")

    assert _prune_stale_skills(skills_dir, keep=set(), dry_run=False) == []
    assert link.is_symlink()
    assert target.is_dir()


def test_sync_skills_nonexistent_repo_fails_fast(tmp_path):
    target = tmp_path / "typo-path"
    result = CliRunner().invoke(sync_skills, [str(target)])
    assert result.exit_code != 0
    assert "不存在" in result.output
    assert not target.exists()


# ---------------------------------------------------------------------------
# 产物可被 skill 解析器读取（round-trip）+ 无 status 键约定
# ---------------------------------------------------------------------------


def _unescape(value: str) -> str:
    """parse_skill_frontmatter 只 strip 引号不反转义——补回 _yaml_quote 的转义。"""
    return value.replace('\\"', '"').replace("\\\\", "\\")


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_frontmatter_roundtrip_via_skill_match_parser(lang):
    i18n.set_lang(lang)
    for dir_name, name, content in _render_all(lang):
        fm = parse_skill_frontmatter(content)
        assert fm["name"] == dir_name
        if name in _STATIC_SKILL_NAMES:
            # 静态资产：name 本身即技能全名（自带 codewiki- 前缀），description
            # 是手写真源，不走 i18n——只校验非空
            assert dir_name == name
            assert len(fm["description"]) >= 10
        else:
            assert dir_name == f"codewiki-{name}"
            expected = i18n.t(f"prompts.{name}.description")
            assert _unescape(fm["description"]) == " ".join(expected.split())
        assert fm["disable-model-invocation"] == "true"
        # 钉死约定：工作流技能不是 skill_creator 两区制产物，不渲染 status
        assert "status" not in fm


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_all_descriptions_meet_min_chars(lang):
    i18n.set_lang(lang)
    for meta in _PROMPT_REGISTRY:
        description = i18n.t(f"prompts.{meta['name']}.description")
        assert len(description) >= 10, f"{meta['name']} description too short"
