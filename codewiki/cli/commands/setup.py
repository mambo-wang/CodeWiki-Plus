"""
setup command for CodeWiki CLI — 三段式一键装机。

一个命令完成项目首装/升级接线的全部三件事（设计定案 2026-10-20）：

1. **hook 段**：为检测到的宿主 IDE 接线 hook 与会话采集——直接复用
   ``ide_config.install_for_ide``（与 ``install-hooks`` 同一实现，capture 默认 on），
   未检测到 IDE 配置目录时打印 SKIP 不算失败；
2. **.mcp.json 段**：在项目根创建/幂等合并 ``.mcp.json``——保留其他
   ``mcpServers`` 与顶层键，``codewiki`` 键存在则覆盖（生成物快照语义）；
   已存在但非法 JSON 时硬报错（用户文件，不替人修复）；
3. **skill 段**：复用 ``sync_skills.sync_repo`` 生成 ``codewiki-*`` 技能文件
   （含静态资产 codewiki-setup）。

分段独立汇报；任一段真失败（异常/写盘错误）exit 1 并指明失败段，另一段
已成功的成果保留不回滚。``--dry-run`` 只拦 .mcp.json 写盘，hook/skill 段
打印执行计划。

与 ``install-hooks`` 的边界：install-hooks 保持单一职责不动；setup 是面向
首装用户的聚合命令（对应 codewiki-setup 技能的第二步）。
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

import click

from codewiki.cli.commands.sync_skills import sync_repo
from codewiki.cli.utils.ide_config import IDE_SPECS, detect_ide_dirs, install_for_ide
from codewiki.mcp import i18n

_MCP_FILE = ".mcp.json"
_MCP_SERVER_KEY = "codewiki"


def _build_server_config(lang: Optional[str]) -> dict[str, Any]:
    """codewiki MCP server 配置块；--lang 显式传入时才写 env.CODEWIKI_LANG。

    timeout 对齐 README 手工配置口径（36000000）；解释器按平台快照（与 TRAE
    hook 命令同口径）：Windows 只保证 ``python``，mac/Linux 普遍只有
    ``python3``，而 MCP 配置无法表达 ``||`` 双解释器回退。
    """
    server: dict[str, Any] = {
        "command": "python" if os.name == "nt" else "python3",
        "args": ["-m", "codewiki.mcp.server"],
        "maxOutputLength": 500000,
        "timeout": 36000000,
        "disabled": False,
    }
    if lang:
        server["env"] = {"CODEWIKI_LANG": lang}
    return server


def _write_mcp_json(repo_path: Path, lang: Optional[str], dry_run: bool) -> str:
    """创建/幂等合并 .mcp.json，返回动作描述（created/updated/preview）。"""
    mcp_path = repo_path / _MCP_FILE
    data: dict[str, Any] = {}
    if mcp_path.is_file():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise click.ClickException(
                f"{mcp_path} 已存在但不是合法 JSON（{e}）。请手工修复后重试——不替用户文件做修复。"
            ) from e
        if not isinstance(data, dict):
            raise click.ClickException(
                f"{mcp_path} 已存在但顶层不是 JSON object。请手工修复后重试。"
            )
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise click.ClickException(f"{mcp_path} 的 mcpServers 不是 JSON object。请手工修复后重试。")
    action = "updated" if _MCP_SERVER_KEY in servers else "created"
    servers[_MCP_SERVER_KEY] = _build_server_config(lang)
    if dry_run:
        return f"preview ({action})"
    mcp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return action


def _run_hook_segment(
    repo_path: Path, ide: Optional[str], capture: Optional[str], dry_run: bool
) -> None:
    """hook 段：复用 install_for_ide；无 IDE 目录 SKIP 不算失败。失败抛异常。"""
    if dry_run:
        click.echo(f"  [plan] install-hooks(ide={ide or 'auto-detect'}, capture={capture or 'on'})")
        return
    capture_on = None if capture is None else capture.lower() == "on"
    if ide:
        target = ide.lower()
        spec = IDE_SPECS[target]
        if spec.get("dir") and not (repo_path / str(spec["dir"])).is_dir():
            raise click.ClickException(
                f"目标目录 {spec['dir']}/ 不存在于 {repo_path}；显式 --ide 不新建配置目录"
                "（可先手工创建，或去掉 --ide 走自动检测）"
            )
        targets = [target]
    else:
        targets = detect_ide_dirs(str(repo_path))
    if not targets:
        click.echo("  SKIP: no IDE config dir detected")
        return
    for name in targets:
        install_for_ide(str(repo_path), name, capture=capture_on, inject_file=None)
        click.echo(f"  [wired] {name}")


def _run_skill_segment(repo_path: Path, ide: Optional[str], lang: str, dry_run: bool) -> None:
    """skill 段：复用 sync_repo。qwenwork 类无配置目录宿主 SKIP。失败抛异常。"""
    if ide and not IDE_SPECS[ide].get("dir"):
        click.echo(f"  SKIP: IDE {ide!r} 无仓库配置目录，不支持技能文件")
        return
    sync_repo(repo_path, lang, ide, dry_run)


@click.command(name="setup")
@click.option(
    "--ide",
    type=click.Choice(list(IDE_SPECS), case_sensitive=False),
    default=None,
    help="只接线指定宿主（hook 段与 skill 段同享）；默认自动检测仓库根 IDE 配置目录",
)
@click.option(
    "--capture",
    type=click.Choice(["on", "off"], case_sensitive=False),
    default=None,
    help="会话采集开关（透传 install-hooks，默认 on）",
)
@click.option(
    "--lang",
    type=click.Choice(["zh", "en"]),
    default=None,
    help="显式指定语言：写入 .mcp.json 的 env.CODEWIKI_LANG，并决定技能文件语言；默认不写 env、按 i18n 解析",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="预览：.mcp.json 不写盘，hook/skill 段打印执行计划",
)
@click.option("--repo-path", type=click.Path(), default=".", help="目标项目路径（默认当前目录）")
def setup(
    ide: Optional[str], capture: Optional[str], lang: Optional[str], dry_run: bool, repo_path: str
) -> None:
    """三段式一键装机：hook 与会话采集 + .mcp.json + 技能文件。

    首装/升级场景一个命令接好全部（对应 codewiki-setup 技能的第二步）：

    \b
    $ codewiki setup                      # 自动检测宿主，三段全做
    $ codewiki setup --lang en            # 技能文件英文 + .mcp.json 注入 CODEWIKI_LANG
    $ codewiki setup --ide trae --dry-run # 只看 trae 的执行计划
    """
    i18n.init_lang()
    if lang:
        i18n.set_lang(lang)
    current = i18n.lang()

    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise click.UsageError(f"目标仓库路径不存在或不是目录：{repo}")
    failures: list[str] = []

    click.echo()
    click.secho(f"Target repo: {repo}" + (" | DRY-RUN" if dry_run else ""), fg="blue", bold=True)

    click.secho("\n[1/3] hooks & capture", fg="blue")
    try:
        _run_hook_segment(repo, ide, capture, dry_run)
    except Exception as e:
        failures.append("hooks")
        click.secho(f"  FAILED: {e}", fg="red")

    click.secho("\n[2/3] .mcp.json", fg="blue")
    try:
        result = _write_mcp_json(repo, lang, dry_run)
        click.echo(f"  [{result}] {repo / _MCP_FILE} (mcpServers.{_MCP_SERVER_KEY})")
    except Exception as e:
        failures.append("mcp")
        click.secho(f"  FAILED: {e}", fg="red")

    click.secho("\n[3/3] skills", fg="blue")
    try:
        _run_skill_segment(repo, ide, current, dry_run)
    except Exception as e:
        failures.append("skills")
        click.secho(f"  FAILED: {e}", fg="red")

    click.echo()
    if failures:
        raise click.ClickException(f"setup 部分失败：{', '.join(failures)} 段（已成功的段不回滚）")
    if dry_run:
        click.secho("Dry run complete - no files written.", fg="yellow")
    else:
        click.secho("OK: setup complete (hooks + .mcp.json + skills).", fg="green")
