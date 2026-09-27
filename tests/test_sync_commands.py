"""Tests for the `sync-commands` CLI command (ADR-0017)."""

import click
import pytest
from click.testing import CliRunner

from codewiki.cli.commands.sync_commands import (
    _default_arguments,
    _filename,
    _host_commands_dir,
    _render_all,
    _render_stub,
    _resolve_targets,
    _slugify_title,
    sync_commands,
)
from codewiki.mcp import i18n
from codewiki.mcp.prompts import _PROMPT_REGISTRY

COUNT = len(_PROMPT_REGISTRY)


@pytest.fixture(autouse=True)
def _fix_lang(monkeypatch):
    """固定语言：屏蔽 init_lang 的环境重读，测试用 set_lang 显式控制。"""
    monkeypatch.setattr(i18n, "init_lang", lambda: None)
    yield
    i18n.set_lang("zh")


def _meta_of(name: str) -> dict:
    return next(m for m in _PROMPT_REGISTRY if m["name"] == name)


# ---------------------------------------------------------------------------
# 渲染：全量覆盖 registry
# ---------------------------------------------------------------------------


def test_render_all_covers_registry():
    rendered = _render_all("zh")
    assert len(rendered) == COUNT
    names = {name for _, name, _ in rendered}
    assert names == {meta["name"] for meta in _PROMPT_REGISTRY}


def test_render_all_zh_filename_is_title_slug():
    rendered = dict((name, filename) for filename, name, _ in _render_all("zh"))
    assert rendered["init-wiki"] == "初始化单仓Wiki工作区.md"


# ---------------------------------------------------------------------------
# 命名：zh 标题 slug / en 用 name
# ---------------------------------------------------------------------------


def test_filename_en_uses_name():
    assert _filename("init-wiki", "初始化单仓Wiki工作区", "en") == "init-wiki.md"
    assert _filename("search-wiki", "搜索 Wiki 知识库", "en") == "search-wiki.md"


def test_filename_zh_uses_title_slug():
    assert _filename("init-wiki", "初始化单仓Wiki工作区", "zh") == "初始化单仓Wiki工作区.md"


def test_slugify():
    assert _slugify_title(" 初始化单仓Wiki工作区 ") == "初始化单仓Wiki工作区"
    assert _slugify_title("搜索 Wiki 知识库") == "搜索-Wiki-知识库"
    assert _slugify_title("a  b") == "a-b"
    assert _slugify_title("???") == "command"


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
# 薄壳内容：指向 get_prompt，不渲染全文
# ---------------------------------------------------------------------------


def test_stub_points_to_get_prompt():
    content = _render_stub("init-wiki", "初始化单仓Wiki工作区", "零配置初始化指引。")
    assert content.startswith("# 初始化单仓Wiki工作区\n")
    assert 'get_prompt(name="init-wiki", arguments={"repo_path": "."})' in content
    assert "以 `get_prompt` 返回内容为准" in content


# ---------------------------------------------------------------------------
# 宿主判定（ADR-0017 决策 3）
# ---------------------------------------------------------------------------


def test_resolve_targets_explicit_ide(tmp_path):
    assert _resolve_targets(str(tmp_path), "qoder") == ["qoder"]
    with pytest.raises(click.UsageError):
        _resolve_targets(str(tmp_path), "codebuddy")  # IDE 自动转化，拒绝生成
    with pytest.raises(click.UsageError):
        _resolve_targets(str(tmp_path), "unknown-ide")


def test_resolve_targets_detect_excludes_codebuddy(tmp_path):
    (tmp_path / ".codebuddy").mkdir()
    (tmp_path / ".qoder").mkdir()
    assert _resolve_targets(str(tmp_path), None) == ["qoder"]


def test_resolve_targets_fallback_trae(tmp_path):
    # 无 .trae 也无非 codebuddy 目录 -> 兜底 .trae 登记处（主动创建）
    assert _resolve_targets(str(tmp_path), None) == ["trae"]


def test_sync_creates_trae_fallback(tmp_path):
    # 无任何 IDE 配置目录：主动创建 .trae/commands/codewiki/ 登记处
    i18n.set_lang("zh")
    runner = CliRunner()
    result = runner.invoke(sync_commands, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    target = tmp_path / ".trae" / "commands" / "codewiki"
    assert target.is_dir()
    assert len(list(target.glob("*.md"))) == COUNT


def test_host_commands_dir(tmp_path):
    assert _host_commands_dir(str(tmp_path), "qoder") == (
        tmp_path / ".qoder" / "commands" / "codewiki"
    )
    assert _host_commands_dir(str(tmp_path), "trae") == (
        tmp_path / ".trae" / "commands" / "codewiki"
    )
    with pytest.raises(click.UsageError):
        _host_commands_dir(str(tmp_path), "qwenwork")  # 无仓库配置目录


# ---------------------------------------------------------------------------
# 写盘：全量覆盖 + 幂等
# ---------------------------------------------------------------------------


def test_sync_writes_and_is_idempotent(tmp_path):
    i18n.set_lang("zh")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_commands, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    target = tmp_path / ".qoder" / "commands" / "codewiki"
    assert target.is_dir()
    assert (target / "初始化单仓Wiki工作区.md").exists()
    assert len(list(target.glob("*.md"))) == COUNT
    # 幂等重跑（全量覆盖，不报错、不翻倍）
    assert runner.invoke(sync_commands, [str(tmp_path)]).exit_code == 0
    assert len(list(target.glob("*.md"))) == COUNT


def test_sync_dry_run_no_write(tmp_path):
    i18n.set_lang("zh")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_commands, ["--dry-run", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert not (tmp_path / ".qoder" / "commands").exists()


def test_sync_en_lang_uses_name_files(tmp_path):
    i18n.set_lang("en")
    (tmp_path / ".qoder").mkdir()
    runner = CliRunner()
    result = runner.invoke(sync_commands, [str(tmp_path)])
    assert result.exit_code == 0, result.output
    target = tmp_path / ".qoder" / "commands" / "codewiki"
    assert (target / "init-wiki.md").exists()
    assert not (target / "初始化单仓Wiki工作区.md").exists()
