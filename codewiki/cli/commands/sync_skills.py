"""
sync-skills command for CodeWiki CLI.

把 `_PROMPT_REGISTRY`（codewiki/mcp/prompts.py，23 条）的每个工作流提示词编译为
宿主 IDE 的技能薄壳（`<宿主配置目录>/skills/codewiki-<name>/SKILL.md`：frontmatter
name/description/disable-model-invocation + get_prompt 调用块，不渲染提示词
全文——权威在 MCP，文件只是可见入口，见 ADR-0019）。

为什么存在（与 ADR-0017 命令薄壳时代的差异）：
- 宿主生态转向 skills 目录；手动触发型 skill（disable-model-invocation: true）
  常驻上下文归零、只能 `/codewiki-<name>` 显式调用，语义等价于「换格式的
  command」——触发仍显式，不引入模型自动路由。
- registry 中标 `"auto": True` 的工作流（知识飞轮类：search-wiki/ingest-note/
  distill-conversations/task-workflow/consolidate-knowledge/skill-creator/
  promote-note）不写 disable-model-invocation，模型可按 description 主动路由，
  用户仍可显式调用。
- IDE 自动映射只有 prompt→command 一条通道（codebuddy），没有 prompt→skill
  通道——codebuddy 不再豁免，与其他宿主一样生成技能薄壳。
- 非 codebuddy 宿主（Qoder/Claude Code/TRAE）原本就依赖本步骤提供可见入口。

宿主判定（ADR-0019 决策 4）：
- ``--ide NAME`` 显式指定 → 只写该宿主的 ``skills/``（qwenwork 无配置目录，拒绝）
- 未指定 → 枚举仓库根 IDE 配置目录（detect_ide_dirs，含 codebuddy），逐个写入
- 目标为空（仓库没有任何 IDE 目录）→ 兜底写 ``.trae/skills/`` 作为仓库级技能
  登记处（agent 读到仓库即知可用技能，不依赖宿主原生识别）

命名（决策 3）：skill 目录名恒为 ``codewiki-<kebab-name>``，不随 locale 变化
（skill name 必须是 ASCII slug；一层拍平布局下目录名即技能名，`codewiki-`
前缀是命名空间等价物）；--lang 决定整文件语言（frontmatter description、
正文样板与开关映射指引均中英双态）。

覆盖（决策 5）：每次执行全量覆盖 + prune——目标目录下不在本次渲染集合内的
``codewiki-*/`` 目录一并删除（只碰前缀，绝不动用户其他技能），文件是生成
快照，权威在 ``get_prompt``，手改无意义。
"""

import shutil
from pathlib import Path
from typing import Any, Optional

import click

from codewiki.cli.utils.ide_config import IDE_SPECS, detect_ide_dirs
from codewiki.mcp import i18n
from codewiki.mcp.prompts import _PROMPT_REGISTRY

# 技能薄壳的安装子目录：<宿主配置目录>/skills/codewiki-<name>/SKILL.md
_SKILLS_SUBDIR = "skills"
# 技能名/目录名前缀：一层拍平布局下的命名空间等价物（与 skill_creator 产出
# 及用户其他技能隔离）
_SKILL_PREFIX = "codewiki-"

# 静态技能资产（随 pip 包分发，codewiki/assets/skills/<name>/SKILL.<lang>.md）。
# codewiki-setup 是「一键装机」入口：要能在未安装 codewiki 的项目里使用，
# 不能进 _PROMPT_REGISTRY 经 get_prompt 获取（鸡生蛋），以静态文件纳入渲染
# 集合——prune 口径（目标目录 codewiki-* 全集 == 渲染集合）保持自洽，
# 该技能也可原样发布到 skillhub 等平台。
_STATIC_SKILLS_DIR = Path(__file__).resolve().parents[2] / "assets" / "skills"
_STATIC_SKILL_NAMES: tuple[str, ...] = ("codewiki-setup",)

# 有默认值的开关参数：不注入 arguments（对齐手写薄壳，避免干扰 get_prompt 默认）
_SWITCH_ARGS = {"enable_task_management", "capture", "clone"}
# 路径类参数：默认 "."（当前目录）
_PATH_ARGS = {"repo_path", "workspace_path"}

_SKILL_TEMPLATE = """---
name: {skill_name}
description: {description_quoted}
{invocation_line}
---

# {title}

{description}

{call_hint}

```
get_prompt(name="{name}"{args_line})
```

{switch_block}{follow_hint}
{truth_hint}
{trigger_hint}
"""

# 正文样板文案中英双态（--lang 决定整文件语言：frontmatter description 与
# 标题/描述走 i18n，正文样板与开关映射指引走本表——en 产物不得残留中文段落）。
# 开关映射指引的语义来源是 2026-09-29 实锤事故（用户答「否」仍被接线）：
# 用户调用技能时附带的相关意愿必须映射进 arguments 再调 get_prompt。
_BODY_I18N: dict[str, dict[str, Any]] = {
    "zh": {
        "call_hint": "调用 MCP 获取完整工作流并按其执行：",
        "switch_head": "可选开关参数（默认值即上述调用；用户调用本技能时附带的相关意愿，先映射进 arguments 再调用 get_prompt，不要丢弃）：",
        "follow_hint": "返回的工作流包含分阶段指引，逐步照做即可。",
        "truth_hint": "不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。",
        "manual_hint": "本技能是手动触发入口（disable-model-invocation: true），不占常驻上下文；由用户显式调用 /{skill_name} 触发。",
        "auto_hint": "本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /{skill_name} 触发。",
        "switch_hints": {
            "enable_task_management": (
                "- enable_task_management：默认启用任务管理接线；"
                '用户明确表示不启用任务管理（如回答「否」/「不要」）时传 "false"'
            ),
            "capture": ('- capture：默认 on；用户明确表示关闭对话采集时传 "off"'),
            "clone": ('- clone：默认 true；用户明确表示只登记不克隆时传 "false"'),
        },
    },
    "en": {
        "call_hint": "Call MCP to fetch the full workflow and follow it:",
        "switch_head": "Optional switches (defaults as in the call above; any related intent the user expresses when invoking this skill must be mapped into arguments before calling get_prompt — do not drop it):",
        "follow_hint": "The returned workflow contains phased instructions — follow them step by step.",
        "truth_hint": "Do not run from memory — the source of truth is `codewiki/mcp/prompts.py`; defer to what `get_prompt` returns.",
        "manual_hint": "This skill is a manual entry point (disable-model-invocation: true): zero standing context, triggered only when the user explicitly invokes /{skill_name}.",
        "auto_hint": "This skill can be auto-invoked by the model on demand (no disable-model-invocation), or explicitly invoked by the user as /{skill_name}.",
        "switch_hints": {
            "enable_task_management": (
                "- enable_task_management: task-management wiring is ON by default; "
                'pass "false" only when the user explicitly declines it (e.g. answers "no")'
            ),
            "capture": (
                '- capture: on by default; pass "off" only when the user '
                "explicitly asks to disable conversation capture"
            ),
            "clone": (
                '- clone: true by default; pass "false" only when the user '
                "explicitly wants registration without cloning"
            ),
        },
    },
}


def _body(lang: str) -> dict[str, Any]:
    """取当前语言的正文样板文案；未知语言回退 zh。"""
    return _BODY_I18N.get(lang) or _BODY_I18N["zh"]


def _yaml_quote(s: str) -> str:
    """frontmatter 标量双引号包裹：压平换行为空格，转义反斜杠与双引号。

    en locale 的 description 含 `": "`，裸写进 frontmatter 是非法 YAML；
    仓内简易解析器（skill_match.parse_skill_frontmatter）按 partition(":")
    取值不受影响，但宿主解析器是真 YAML，必须引用。
    """
    flattened = " ".join(s.split())
    escaped = flattened.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _default_arguments(meta: dict) -> str:
    """从 registry 元数据构造 get_prompt arguments 的 JSON 片段（'' 表示省略）。

    规则（对齐现有手写薄壳，可复现）：
    - repo_path / workspace_path -> "."
    - 开关参数（enable_task_management/capture/clone）不注入
    - 其余参数 -> "<参数名>" 占位（Agent 执行时按需填写）
    """
    pairs = []
    for arg_name, _required in meta.get("args", []):
        if arg_name in _SWITCH_ARGS:
            continue
        value = "." if arg_name in _PATH_ARGS else f"<{arg_name}>"
        pairs.append(f'"{arg_name}": "{value}"')
    if not pairs:
        return ""
    return "{" + ", ".join(pairs) + "}"


def _switch_block(meta: dict, lang: str) -> str:
    """含开关参数的 prompt 生成映射指引段；无开关参数返回空串。

    开关参数不注入 arguments（默认值生效），但薄壳必须告诉 Agent：
    用户调用技能时附带的相关意愿（如「不要启用任务管理」）要映射进
    arguments 再调 get_prompt——这是意愿到达 prompt 渲染层的唯一通道。
    """
    body = _body(lang)
    hints_map: dict[str, str] = body["switch_hints"]
    hints = [
        hints_map[arg_name] for arg_name, _required in meta.get("args", []) if arg_name in hints_map
    ]
    if not hints:
        return ""
    return str(body["switch_head"]) + "\n" + "\n".join(hints) + "\n\n"


def _render_skill(name: str, title: str, description: str, lang: str) -> str:
    """渲染单个技能薄壳（SKILL.md 全文，整文件语言跟随 lang）。"""
    meta: dict = {"args": []}
    for entry in _PROMPT_REGISTRY:
        if entry["name"] == name:
            meta = entry
            break
    args_line = ""
    arguments = _default_arguments(meta)
    if arguments:
        args_line = f", arguments={arguments}"
    skill_name = f"{_SKILL_PREFIX}{name}"
    body = _body(lang)
    if meta.get("auto"):
        # 自动触发型：不写 disable-model-invocation，模型可按 description 主动路由
        invocation_line = "# model-invocable"
        hint = str(body["auto_hint"]).format(skill_name=skill_name)
    else:
        invocation_line = "disable-model-invocation: true"
        hint = str(body["manual_hint"]).format(skill_name=skill_name)
    return _SKILL_TEMPLATE.format(
        skill_name=skill_name,
        description_quoted=_yaml_quote(description),
        invocation_line=invocation_line,
        title=title,
        description=description,
        call_hint=body["call_hint"],
        name=name,
        args_line=args_line,
        switch_block=_switch_block(meta, lang),
        follow_hint=body["follow_hint"],
        truth_hint=body["truth_hint"],
        trigger_hint=hint,
    )


def _host_skills_dir(repo: str, ide: str) -> Path:
    spec = IDE_SPECS.get(ide)
    if not spec or not spec.get("dir"):
        raise click.UsageError(f"IDE {ide!r} 无仓库配置目录，不支持技能文件（如 qwenwork）")
    return Path(repo) / str(spec["dir"]) / _SKILLS_SUBDIR


def _resolve_targets(repo: str, explicit_ide: Optional[str]) -> list[str]:
    """宿主判定（ADR-0019 决策 4）：显式 --ide > 枚举全部 IDE 目录 > 兜底 .trae。

    codebuddy 不再豁免：IDE 自动映射只有 prompt→command 通道，没有
    prompt→skill 通道，codebuddy 与其他宿主一样需要生成技能薄壳。
    兜底无条件写 `.trae/skills/`（仓库级技能登记处），.trae 不存在时主动
    创建——保证任何项目执行初始化后都有技能入口。
    """
    if explicit_ide:
        if explicit_ide not in IDE_SPECS:
            raise click.UsageError(
                f"未知 IDE {explicit_ide!r}。支持：{', '.join(sorted(IDE_SPECS))}"
            )
        if not IDE_SPECS[explicit_ide].get("dir"):
            raise click.UsageError(
                f"IDE {explicit_ide!r} 无仓库配置目录，不支持技能文件（如 qwenwork）"
            )
        return [explicit_ide]
    targets = detect_ide_dirs(repo)
    if not targets:
        # 兜底：仓库级技能登记处（不依赖宿主原生识别，agent 读到仓库即知可用技能）
        targets = ["trae"]
    return targets


def _render_static(lang: str) -> list[tuple[str, str, str]]:
    """读取静态技能资产（SKILL.<lang>.md，未知语言回退 zh），返回 [(目录名, 技能名, 内容)]。"""
    results = []
    for name in _STATIC_SKILL_NAMES:
        src = _STATIC_SKILLS_DIR / name / f"SKILL.{lang}.md"
        if not src.is_file():
            src = _STATIC_SKILLS_DIR / name / "SKILL.zh.md"
        results.append((name, name, src.read_text(encoding="utf-8")))
    return results


def _render_all(lang: str) -> list[tuple[str, str, str]]:
    """渲染全部技能薄壳（registry 编译产物 + 静态资产），返回 [(目录名, 名称, 内容)]。"""
    results = []
    for meta in _PROMPT_REGISTRY:
        name = meta["name"]
        title = i18n.t(f"prompts.{name}.title")
        description = i18n.t(f"prompts.{name}.description")
        content = _render_skill(name, title, description, lang)
        results.append((f"{_SKILL_PREFIX}{name}", name, content))
    results.extend(_render_static(lang))
    return results


def _prune_stale_skills(target_dir: Path, keep: set[str], dry_run: bool) -> list[str]:
    """删除目标目录下不在 keep 集合内的 codewiki- 前缀目录（生成快照口径）。

    只碰 ``_SKILL_PREFIX`` 前缀目录，用户其他技能一律不动；目标目录不存在
    时无操作。返回被删除（或 dry-run 下将被删除）的目录名列表。
    """
    if not target_dir.is_dir():
        return []
    pruned = []
    for entry in sorted(target_dir.iterdir()):
        if (
            entry.is_dir()
            and not entry.is_symlink()
            and entry.name.startswith(_SKILL_PREFIX)
            and entry.name not in keep
        ):
            pruned.append(entry.name)
            if not dry_run:
                shutil.rmtree(entry)
    return pruned


def sync_repo(repo_path: Path, lang: str, ide: Optional[str], dry_run: bool) -> tuple[int, int]:
    """把渲染集合写入目标宿主 skills 目录（全量覆盖 + prune），返回 (技能数, 宿主数)。

    sync-skills 命令与 setup 的 skill 段共用本函数；调用方负责 i18n 语言设定。
    """
    targets = _resolve_targets(str(repo_path), ide)
    rendered = _render_all(lang)
    keep = {dir_name for dir_name, _, _ in rendered}

    click.echo(
        f"Language: {lang} | Skills: {len(rendered)} | "
        f"Targets: {', '.join(targets)}" + (" | DRY-RUN" if dry_run else "")
    )

    for target in targets:
        target_dir = _host_skills_dir(str(repo_path), target)
        click.echo(f"[{target}] -> {target_dir}{'/'}")
        for dir_name in sorted(_prune_stale_skills(target_dir, keep, dry_run)):
            click.echo(f"  [prune{'preview' if dry_run else 'd'}] {dir_name}{'/'}")
        for dir_name, _, content in rendered:
            if dry_run:
                click.echo(f"  [preview] {dir_name}/SKILL.md")
            else:
                skill_dir = target_dir / dir_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
                click.echo(f"  [written] {dir_name}/SKILL.md")

    return len(rendered), len(targets)


@click.command(name="sync-skills")
@click.option(
    "--lang",
    type=click.Choice(["zh", "en"]),
    default=None,
    help="技能文件语言（frontmatter description + 正文全部内容，中英双态）；默认按 i18n 解析（config.lang > CODEWIKI_LANG > OS locale > zh）",
)
@click.option(
    "--ide",
    type=str,
    default=None,
    help="显式指定宿主 IDE（如 qoder/trae/codebuddy）；默认枚举仓库根 IDE 配置目录",
)
@click.option("--dry-run", is_flag=True, help="只预览目标与技能清单（含 prune），不写盘")
@click.argument("repo", required=False, default=".")
def sync_skills(lang: Optional[str], ide: Optional[str], dry_run: bool, repo: str) -> None:
    """把全部工作流提示词编译为宿主技能文件（技能薄壳，ADR-0019）。

    生成 `<宿主配置目录>/skills/codewiki-<name>/SKILL.md`，每个文件只写
    如何获取全文（get_prompt 调用块），权威仍在 MCP。默认手动触发型
    （disable-model-invocation: true）；registry 标 `"auto": True` 的
    工作流不写该开关，模型可主动调用。init-wiki / init-workspace
    执行时会指示调用本命令。ADR-0017 时代的 `commands/codewiki/*.md`
    存量命令薄壳本命令不清理，需手工删除一次。

    渲染集合除 registry 编译产物外还含静态资产（codewiki-setup，见
    `_STATIC_SKILL_NAMES`）——prune 以集合为准，不会被误删。
    """
    i18n.init_lang()
    if lang:
        i18n.set_lang(lang)
    current = i18n.lang()

    repo_path = Path(repo).resolve()
    if not repo_path.is_dir():
        raise click.UsageError(f"目标仓库路径不存在或不是目录：{repo_path}")

    click.echo()
    click.secho(f"Target repo: {repo_path}", fg="blue", bold=True)
    skill_count, host_count = sync_repo(repo_path, current, ide, dry_run)

    click.echo()
    if dry_run:
        click.secho("Dry run complete - no files written.", fg="yellow")
    else:
        click.secho(
            f"OK: {skill_count} skill stubs synced to {host_count} host(s).",
            fg="green",
        )
