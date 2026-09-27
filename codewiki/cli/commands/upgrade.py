# -*- coding: utf-8 -*-
"""`codewiki upgrade` — 前台升级子命令（Q9）。

设计定案见 codewiki/utils/self_update.py 模块 docstring 与 repowiki 笔记
2026-09-24（rename-aside 自动升级）。
"""

from __future__ import annotations

import click

from codewiki.utils import self_update


@click.command(name="upgrade")
@click.option("--check", is_flag=True, help="只查询 PyPI 新版本，不安装")
def upgrade_command(check: bool):
    """升级 codewiki-plus 到最新版本。

    自动升级（后台、无感知）默认开启，可用 CODEWIKI_NO_AUTOUPDATE=1 关闭；
    本命令是显式的前台升级入口，输出结果立即可见。
    """
    if check:
        latest = self_update.check_latest()
        from codewiki import __version__

        if latest is None:
            click.secho("✗ 无法查询 PyPI（网络不可达或超时）", fg="red")
            raise SystemExit(1)
        if self_update._parse_version(latest) == self_update._parse_version(__version__):
            click.echo(f"已是最新版本 v{__version__}")
        else:
            click.echo(f"当前 v{__version__}，最新 v{latest}")
            if not self_update._auto_upgradable(__version__, latest):
                click.secho("（major 版本变更，自动升级不会安装，需手动执行）", fg="yellow")
        return

    raise SystemExit(self_update.run_foreground_upgrade())
