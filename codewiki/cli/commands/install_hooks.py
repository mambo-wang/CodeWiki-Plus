"""
Install-hooks command for CodeWiki CLI.

用户触发创建/启用 hook 时自动检测项目根目录存在的智能体配置目录
（.codebuddy/.qoder/.claude），检测到哪些就为哪些智能体接线——
拷贝 hook 脚本与 distill-worker subagent、合并 settings.json hook 注册、
写入 AGENTS.md 任务记忆引导段。千问办公（QwenWork）无 shell hook 机制，
走 prompt 接线（AGENTS.md 协议段，Agent 中介捕获），仅显式 --ide qwenwork
触发（仓库无标记目录，不参与自动检测）。
"""

import sys
from pathlib import Path

import click

from codewiki.cli.utils.errors import handle_error
from codewiki.cli.utils.ide_config import (
    IDE_SPECS,
    IdeWiringError,
    detect_ide_dirs,
    install_for_ide,
)


def _echo_summary(repo: str, results: list[dict]) -> None:
    """输出每个 IDE 的接线结果摘要（仅用 ASCII 符号，兼容 Windows GBK 控制台）。"""
    click.echo()
    click.secho(f"Target repo: {repo}", fg="blue", bold=True)
    for r in results:
        if r.get("wiring") == "prompt":
            # prompt 模式（千问办公）：无目录/脚本/注册，只有 AGENTS.md 协议段
            click.secho(f"\n[{r['ide']}] -> AGENTS.md (prompt wiring)", fg="cyan", bold=True)
            if r.get("protocol_changed"):
                click.secho("  [updated] AGENTS.md QwenWork capture protocol", fg="green")
            else:
                click.echo("  [no-change] AGENTS.md QwenWork capture protocol present")
            if r["agents_changed"]:
                click.secho("  [updated] AGENTS.md task-memory section", fg="green")
            else:
                click.echo("  [no-change] AGENTS.md task-memory section present")
            continue
        click.secho(f"\n[{r['ide']}] -> {r['dir']}/", fg="cyan", bold=True)
        for copied in r["copied"]:
            click.echo(f"  [copied] {copied}")
        if r["settings_written"]:
            if r["settings_changed"]:
                click.secho("  [updated] settings.json", fg="green")
            else:
                click.echo("  [no-change] settings.json already wired")
        if r["agents_changed"]:
            click.secho("  [updated] AGENTS.md task-memory section", fg="green")
        else:
            click.echo("  [no-change] AGENTS.md task-memory section present")
    click.secho("\nHook wiring complete.", fg="green", bold=True)


@click.command(name="install-hooks")
@click.option(
    "--ide",
    type=click.Choice(list(IDE_SPECS), case_sensitive=False),
    default=None,
    help=(
        "Wire a specific IDE only, skipping auto-detection. One of: "
        + ", ".join(IDE_SPECS)
        + ". The IDE's config dir must already exist; pass --create-dir to"
        " create it."
    ),
)
@click.option(
    "--create-dir",
    "create_dir",
    is_flag=True,
    default=False,
    help=(
        "With --ide only: allow wiring an IDE whose config dir does not"
        " exist yet in the repo (the dir will be created). Safety gate:"
        " without this flag, --ide never conjures new IDE config dirs."
    ),
)
@click.option(
    "--repo-path",
    type=click.Path(),
    default=".",
    help="Target project path (default: current directory)",
)
def install_hooks(ide: str, create_dir: bool, repo_path: str) -> None:
    """
    Wire CodeWiki task-memory hooks/subagents for detected IDEs.

    无 --ide 参数时自动检测项目根目录存在的智能体配置目录
    （.codebuddy/.qoder/.claude），检测到哪些就为哪些接线。
    每个 IDE 接线内容：强制拷贝 hook 脚本与 distill-worker subagent 到
    对应目录、幂等合并 settings.json 的 SessionStart/SessionEnd 注册、
    向 AGENTS.md upsert 任务记忆引导段（多 IDE 共享一份）。

    Examples:

    \b
    # Auto-detect IDEs in the current project and wire all found
    $ codewiki install-hooks

    \b
    # Auto-detect in a specific project
    $ codewiki install-hooks --repo-path /path/to/project

    \b
    # Wire a specific IDE only (skip detection)
    $ codewiki install-hooks --ide qoder
    """
    try:
        if ide:
            target = ide.lower()
            spec = IDE_SPECS[target]
            if spec.get("dir") and not create_dir:
                ide_dir = Path(repo_path) / spec["dir"]
                if not ide_dir.is_dir():
                    raise IdeWiringError(
                        f"target dir {spec['dir']}/ does not exist in {repo_path}. "
                        "Explicit --ide wiring does not create missing IDE config "
                        "dirs (a repo should only be wired for tools actually "
                        "used in it). Re-run with --create-dir if you really "
                        f"want to wire {target} into this repo."
                    )
            targets = [target]
        else:
            if create_dir:
                raise IdeWiringError("--create-dir only makes sense together with --ide <name>.")
            targets = detect_ide_dirs(repo_path)
        if not targets:
            click.secho(
                "No supported IDE config dir detected in the project root.",
                fg="yellow",
            )
            click.echo("Detected dirs: .codebuddy / .qoder / .claude")
            click.echo(
                "QwenWork (prompt wiring) has no repo marker and is never"
                " auto-detected - wire it explicitly with --ide qwenwork"
            )
            click.echo(
                "To wire a specific IDE whose config dir already exists, use: "
                "codewiki install-hooks --ide <" + "|".join(IDE_SPECS) + ">"
            )
            click.echo(
                "(--ide requires the IDE config dir to exist; add --create-dir"
                " only if you deliberately want to create it)"
            )
            sys.exit(0)
        results = [install_for_ide(repo_path, name) for name in targets]
        _echo_summary(repo_path, results)
    except IdeWiringError as e:
        click.secho(f"\nError: hook wiring failed: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        sys.exit(handle_error(e))
