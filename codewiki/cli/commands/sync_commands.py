"""
sync-commands command for CodeWiki CLI.

把 `_PROMPT_REGISTRY`（codewiki/mcp/prompts.py，23 条）的每个工作流提示词编译为
宿主 IDE 的斜杠命令文件（命令薄壳：标题 + 描述 + get_prompt 调用块 + 真源提示，
不渲染提示词全文——权威在 MCP，文件只是可见入口，见 ADR-0017）。

为什么存在：
- Trae/codebuddy 宿主 IDE 自动把 MCP prompt 映射为命令，仓库内为它再生成命令文件
  是重复劳动（.codebuddy 忽略）。
- 非 codebuddy 宿主（本仓库实测 Qoder）没有这条自动通道：它们各自识别自己的
  commands 目录（`.qoder/commands/`、`.claude/commands/`……），薄壳命令文件给出
  可见入口，Agent 执行斜杠命令即得"如何获取全文"的指引。

宿主判定（ADR-0017 决策 3）：
- ``--ide NAME`` 显式指定 → 只写该宿主的 ``commands/codewiki/``（codebuddy 被拒绝）
- 未指定 → 枚举仓库根 IDE 配置目录（detect_ide_dirs），排除 codebuddy，逐个写入
- 目标为空（仓库没有任何非 codebuddy IDE 目录）→ 兜底写 ``.trae/commands/codewiki/``
  作为仓库级命令登记处（agent 读到仓库即知可用命令，不依赖宿主原生识别）

命名（决策 4）：文件名语言跟随 i18n locale 定格——zh 用当前语言标题的 slug
（如 ``初始化单仓Wiki工作区.md``），en 用 prompt 的 name（kebab-case）。

覆盖（决策 7）：每次执行全量覆盖，不做锚点/哈希保护——文件是生成快照，权威在
``get_prompt``，手改无意义。
"""

import re
from pathlib import Path
from typing import Optional

import click

from codewiki.cli.utils.ide_config import IDE_SPECS, detect_ide_dirs
from codewiki.mcp import i18n
from codewiki.mcp.prompts import _PROMPT_REGISTRY

# 命令薄壳的安装子目录：<宿主配置目录>/commands/codewiki/
_COMMANDS_SUBDIR = "commands/codewiki"

# 有默认值的开关参数：不注入 arguments（对齐手写薄壳，避免干扰 get_prompt 默认）
_SWITCH_ARGS = {"enable_task_management", "capture", "clone"}
# 路径类参数：默认 "."（当前目录）
_PATH_ARGS = {"repo_path", "workspace_path"}

_STUB_TEMPLATE = """# {title}

{description}

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="{name}"{args_line})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
"""


def _slugify_title(title: str) -> str:
    """文件名化标题：保留 CJK/字母/数字/连字符，其余字符折叠为连字符。"""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title.strip(), flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "command"


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


def _render_stub(name: str, title: str, description: str) -> str:
    """渲染单个命令薄壳。"""
    meta = {"args": []}
    for entry in _PROMPT_REGISTRY:
        if entry["name"] == name:
            meta = entry
            break
    args_line = ""
    arguments = _default_arguments(meta)
    if arguments:
        args_line = f", arguments={arguments}"
    return _STUB_TEMPLATE.format(
        title=title, description=description, name=name, args_line=args_line
    )


def _filename(name: str, title: str, lang: str) -> str:
    """zh 用当前语言标题 slug；en 用 prompt 的 name（kebab-case）。"""
    if lang == "zh":
        return _slugify_title(title) + ".md"
    return name + ".md"


def _host_commands_dir(repo: str, ide: str) -> Path:
    spec = IDE_SPECS.get(ide)
    if not spec or not spec.get("dir"):
        raise click.UsageError(f"IDE {ide!r} 无仓库配置目录，不支持命令文件（如 qwenwork）")
    return Path(repo) / spec["dir"] / _COMMANDS_SUBDIR


def _resolve_targets(repo: str, explicit_ide: Optional[str]) -> list[str]:
    """宿主判定（ADR-0017 决策 3）：显式 --ide > 枚举非 codebuddy > 兜底 .trae。

    兜底无条件写 `.trae/commands/codewiki/`（仓库级命令登记处），.trae 不存在时
    主动创建——保证任何项目执行初始化后都有命令入口（登记处不依赖宿主原生识别，
    agent 读到仓库即知可用命令）。
    """
    if explicit_ide:
        if explicit_ide == "codebuddy":
            raise click.UsageError(
                "codebuddy 会由 IDE 自动把 MCP prompt 转为命令，仓库内无需生成命令文件"
            )
        if explicit_ide not in IDE_SPECS:
            raise click.UsageError(
                f"未知 IDE {explicit_ide!r}。支持：{', '.join(sorted(IDE_SPECS))}"
            )
        return [explicit_ide]
    targets = [ide for ide in detect_ide_dirs(repo) if ide != "codebuddy"]
    if not targets:
        # 兜底：仓库级命令登记处（不依赖宿主原生识别，agent 读到仓库即知可用命令）
        targets = ["trae"]
    return targets


def _render_all(lang: str) -> list[tuple[str, str, str]]:
    """渲染全部 prompt 的命令薄壳，返回 [(文件名, 目录内相对路径, 内容)]。"""
    results = []
    for meta in _PROMPT_REGISTRY:
        name = meta["name"]
        title = i18n.t(f"prompts.{name}.title")
        description = i18n.t(f"prompts.{name}.description")
        content = _render_stub(name, title, description)
        results.append((_filename(name, title, lang), name, content))
    return results


@click.command(name="sync-commands")
@click.option(
    "--lang",
    type=click.Choice(["zh", "en"]),
    default=None,
    help="命令文件语言（文件名+标题/描述）；默认按 i18n 解析（config.lang > CODEWIKI_LANG > OS locale > zh）",
)
@click.option(
    "--ide",
    type=str,
    default=None,
    help="显式指定宿主 IDE（如 qoder/trae）；默认枚举仓库根 IDE 配置目录，排除 codebuddy",
)
@click.option("--dry-run", is_flag=True, help="只预览目标与文件清单，不写盘")
@click.argument("repo", required=False, default=".")
def sync_commands(lang: Optional[str], ide: Optional[str], dry_run: bool, repo: str) -> None:
    """把全部工作流提示词编译为宿主命令文件（命令薄壳，ADR-0017）。

    生成 `<宿主配置目录>/commands/codewiki/*.md`，每个文件只写如何获取全文
    （get_prompt 调用块），权威仍在 MCP。codebuddy 由 IDE 自动转化 prompt→command，
    跳过。init-wiki / init-workspace 执行时会指示调用本命令。
    """
    i18n.init_lang()
    if lang:
        i18n.set_lang(lang)
    current = i18n.lang()

    repo_path = Path(repo).resolve()
    targets = _resolve_targets(str(repo_path), ide)
    rendered = _render_all(current)

    click.echo()
    click.secho(f"Target repo: {repo_path}", fg="blue", bold=True)
    click.echo(
        f"Language: {current} | Prompts: {len(rendered)} | "
        f"Targets: {', '.join(targets)}" + (" | DRY-RUN" if dry_run else "")
    )

    for target in targets:
        target_dir = _host_commands_dir(str(repo_path), target)
        click.echo(f"\n[{target}] -> {target_dir}{'/'}")
        for filename, _, content in rendered:
            if dry_run:
                click.echo(f"  [preview] {filename}")
            else:
                target_dir.mkdir(parents=True, exist_ok=True)
                (target_dir / filename).write_text(content, encoding="utf-8")
                click.echo(f"  [written] {filename}")

    click.echo()
    if dry_run:
        click.secho("Dry run complete - no files written.", fg="yellow")
    else:
        click.secho(
            f"OK: {len(rendered)} command stubs synced to {len(targets)} host(s).",
            fg="green",
        )
