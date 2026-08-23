"""
Install-hooks command for CodeWiki CLI.

用户触发创建/启用 hook 时自动检测项目根目录存在的智能体配置目录
（.codebuddy/.qoder/.claude），检测到哪些就为哪些智能体接线——
拷贝 hook 脚本与 distill-worker subagent、合并 settings.json hook 注册、
写入 AGENTS.md 任务记忆引导段。
"""

import sys

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
        "Wire a specific IDE only, skipping auto-detection. "
        "One of: " + ", ".join(IDE_SPECS)
    ),
)
@click.option(
    "--repo-path",
    type=click.Path(),
    default=".",
    help="Target project path (default: current directory)",
)
def install_hooks(ide: str, repo_path: str) -> None:
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
            targets = [ide.lower()]
        else:
            targets = detect_ide_dirs(repo_path)
        if not targets:
            click.secho(
                "No supported IDE config dir detected in the project root.",
                fg="yellow",
            )
            click.echo("Detected dirs: .codebuddy / .qoder / .claude")
            click.echo(
                "To wire a specific IDE regardless, use: "
                "codewiki install-hooks --ide <"
                + "|".join(IDE_SPECS)
                + ">"
            )
            sys.exit(0)
        results = [install_for_ide(repo_path, name) for name in targets]
        _echo_summary(repo_path, results)
    except IdeWiringError as e:
        click.secho(f"\nError: hook wiring failed: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        sys.exit(handle_error(e))
