# -*- coding: utf-8 -*-
"""codewiki-plus 无感知自动升级（设计定案见 repowiki 笔记 2026-09-24 rename-aside）。

核心约束（全部经真机探针实测，Windows 11 + Python 3.12 venv）：
  - 加载中的 .pyd 不可写、不可删，但**可重命名**（rename-aside 技巧）；
  - DETACHED_PROCESS 子进程在父进程退出后存活（wait-for-exit 兜底）。

主进程职责刻意收窄为「读本地状态文件 + 派生 detached 子进程」，微秒级、
零网络、零阻塞——MCP server 启动握手不受影响（Q12）。PyPI 查询、版本
决策、pip 安装全部发生在子进程里。

升级策略（Q6 混合）：
  - 纯 Python 改动 → rename-aside：被锁 .pyd 重命名到 .old，pip 立即写入
    新版，下次启动生效并清理 .old 残留；
  - tree-sitter 系列原生依赖版本变动（比较 PyPI requires_dist）→ 退回
    wait-for-exit：detached 子进程等父进程退出后再 pip install。

安全网：
  - CODEWIKI_NO_AUTOUPDATE 环境变量 / config.json autoupdate=false 退出（Q1）；
  - 仅纯 pip/uv venv 启用；pipx/uv tool/conda/源码安装跳过（Q2）；
  - semver 闸门：patch+minor 自动升，major 只提示（Q3）；
  - ~/.codewiki/.autoupdate.lock 互斥，10 分钟超时抢占（Q8）；
  - 升级后首次启动健康自检：元数据版本 ≠ import 版本 → 重装自愈（Q4/Q10）。

fail-open 铁律：本模块任何失败（网络、权限、解析……）一律静默跳过，
绝不影响主功能。
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PACKAGE_NAME = "codewiki-plus"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PACKAGE_NAME}/json"
CHECK_INTERVAL = 24 * 3600  # 每天最多查一次（Q7）
LOCK_TIMEOUT = 10 * 60  # 互斥锁超时抢占（Q8）
WAIT_FOR_EXIT_TIMEOUT = 60 * 60  # wait-for-exit 最长等待一个会话周期

# 原生依赖前缀：这些包的版本变动意味着 ABI 风险，退回保守路径（Q6）
NATIVE_DEP_PREFIXES = ("tree-sitter",)

STATE_DIR = Path.home() / ".codewiki"
STATE_FILE = STATE_DIR / "autoupdate.json"
LOCK_FILE = STATE_DIR / ".autoupdate.lock"


# ===================================================================
#  状态文件（Q7）
# ===================================================================


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(data: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # fail-open


# ===================================================================
#  环境闸门（Q1/Q2）
# ===================================================================


def _autoupdate_disabled() -> bool:
    if os.environ.get("CODEWIKI_NO_AUTOUPDATE", "").strip() in ("1", "true", "yes"):
        return True
    try:
        cfg = json.loads((STATE_DIR / "config.json").read_text(encoding="utf-8"))
        return cfg.get("autoupdate") is False
    except (OSError, json.JSONDecodeError):
        return False


def _is_source_install() -> bool:
    """源码运行（editable / CODEWIKI_HOME 指向 checkout）→ 跳过。"""
    if os.environ.get("CODEWIKI_HOME"):
        return True
    try:
        from importlib.metadata import distribution

        dist = distribution(PACKAGE_NAME)
        direct_url = dist.read_text("direct_url.json")
        if direct_url:
            return True  # editable / local install
    except Exception:
        return True  # 连 distribution 都找不到 → 不是正常 pip 安装
    return False


def _managed_env() -> bool:
    """pipx / uv tool / conda 环境不自动升级，只提示手动命令（Q2）。"""
    prefix = str(Path(sys.prefix))
    if "pipx" in prefix or os.environ.get("PIPX_HOME"):
        return False
    if re.search(r"[\\/]uv[\\/]tools?[\\/]", prefix):
        return False
    if os.environ.get("CONDA_DEFAULT_ENV") and "conda" in prefix.lower():
        return False
    return True


def _eligible() -> bool:
    return not _autoupdate_disabled() and not _is_source_install() and _managed_env()


# ===================================================================
#  版本比较（Q3 semver 闸门）
# ===================================================================

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _parse_version(v: str) -> Optional[tuple]:
    m = _VERSION_RE.match(v.strip())
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def _auto_upgradable(current: str, latest: str) -> bool:
    """patch+minor 自动升；major 只提示（Q3）。"""
    c, new = _parse_version(current), _parse_version(latest)
    if not c or not new:
        return False
    return c < new and c[0] == new[0]


# ===================================================================
#  互斥锁（Q8）
# ===================================================================


class _UpdateLock:
    """O_CREAT|O_EXCL 原子创建；超时视为死锁自动抢占。"""

    def __init__(self, timeout: int = LOCK_TIMEOUT):
        self.timeout = timeout
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            self._fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self._fd, str(os.getpid()).encode())
            return True
        except FileExistsError:
            try:
                age = time.time() - LOCK_FILE.stat().st_mtime
                if age > self.timeout:
                    LOCK_FILE.unlink()  # 死锁抢占
                    return self.acquire()
            except OSError:
                pass
            return False
        except OSError:
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


# ===================================================================
#  detached 升级子进程
# ===================================================================

# 子进程脚本：自包含全部决策逻辑（PyPI 查询、semver 闸门、模式决策、
# rename-aside），不 import codewiki——避免与父进程已加载模块版本混跑，
# 也避免父进程升级后子脚本引用的函数消失。
_CHILD_SCRIPT = r"""
import json, os, re, subprocess, sys, time
import urllib.request
from pathlib import Path

state_file, package, current_version, wait_timeout = (
    sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))

PYPI_JSON_URL = "https://pypi.org/pypi/%s/json" % package
NATIVE_DEP_PREFIXES = ("tree-sitter",)
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")

def write_state(**kw):
    try:
        s = {}
        try:
            s = json.loads(open(state_file, encoding="utf-8").read())
        except Exception:
            pass
        s.update(kw)
        open(state_file, "w", encoding="utf-8").write(json.dumps(s, indent=2))
    except Exception:
        pass

def fetch_pypi():
    with urllib.request.urlopen(PYPI_JSON_URL, timeout=3) as resp:
        return json.loads(resp.read().decode())

def parse_version(v):
    m = VERSION_RE.match(v.strip())
    return tuple(int(x) for x in m.groups()) if m else None

def native_reqs(info):
    return sorted(
        r.split(";")[0].strip()
        for r in (info.get("requires_dist") or [])
        if any(r.startswith(p) for p in NATIVE_DEP_PREFIXES))

# ---- 1. 查询 + 决策（fail-open：任何失败直接退出，不写 failed） ----
try:
    data = fetch_pypi()
except Exception:
    sys.exit(0)  # 网络失败 → 等下个周期，不算失败

latest = data["info"]["version"]
cur, new = parse_version(current_version), parse_version(latest)
if not cur or not new or not (cur < new and cur[0] == new[0]):
    sys.exit(0)  # 无新版 / major 变更 / 解析失败 → 不自动升

# ---- 2. 模式决策：原生依赖约束变化 → wait-for-exit，否则 rename-aside ----
try:
    from importlib.metadata import requires
    current_native = sorted(
        r.split(";")[0].strip()
        for r in (requires(package) or [])
        if any(r.startswith(p) for p in NATIVE_DEP_PREFIXES))
except Exception:
    current_native = None  # 查不到 → 保守路径

native_changed = current_native is None or native_reqs(data["info"]) != current_native
mode = "wait-for-exit" if native_changed else "rename-aside"

# ---- 3. wait-for-exit：等父进程退出（Windows 轮询句柄 / POSIX ppid 变化） ----
if mode == "wait-for-exit":
    deadline = time.time() + wait_timeout
    parent = os.getppid()
    while time.time() < deadline:
        try:
            if os.name == "nt":
                import ctypes
                SYNCHRONIZE = 0x00100000
                h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, parent)
                if not h:
                    break  # 父进程已退出
                ctypes.windll.kernel32.CloseHandle(h)
            else:
                if os.getppid() != parent:
                    break
        except Exception:
            break
        time.sleep(2)
    # 超时后仍尝试一次——锁可能已被中途重启释放

# ---- 4. rename-aside：仅当 pip 将重装原生包时，把被锁文件挪到 .old ----
def rename_locked_native_modules():
    site = Path(sys.prefix)
    for prefix in NATIVE_DEP_PREFIXES:
        for pattern in (
            "Lib/site-packages/%s*/**/*.pyd" % prefix,
            "lib/python*/site-packages/%s*/**/*.so*" % prefix,
        ):
            for p in site.glob(pattern):
                old = p.with_suffix(p.suffix + ".old")
                try:
                    p.rename(old)
                except OSError:
                    pass  # 未被锁的会被 pip 正常覆盖，无需处理

if mode == "rename-aside":
    rename_locked_native_modules()

# ---- 5. pip 安装 ----
try:
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "%s==%s" % (package, latest)],
        capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        write_state(last_result="failed", last_error=r.stderr[-2000:])
        sys.exit(0)
except Exception as e:
    write_state(last_result="failed", last_error=str(e)[:2000])
    sys.exit(0)

write_state(last_result="upgraded", last_version=latest)
"""


def cleanup_stale_old_files() -> None:
    """启动时清理上次 rename-aside 留下的 .old 残留（旧句柄已释放）。"""
    try:
        site = Path(sys.prefix)
        for prefix in NATIVE_DEP_PREFIXES:
            for pattern in (
                f"Lib/site-packages/{prefix}*/**/*.pyd.old",
                f"lib/python*/site-packages/{prefix}*/**/*.so*.old",
            ):
                for p in site.glob(pattern):
                    try:
                        p.unlink()
                    except OSError:
                        pass  # 仍被锁（还有别的进程没退）→ 留给下次
    except Exception:
        pass  # fail-open


def _spawn_updater() -> None:
    """派生 detached 子进程执行升级，主进程立即返回。

    子脚本自包含全部决策（PyPI 查询、semver 闸门、模式选择），主进程
    只传状态文件路径、包名、当前版本号。
    """
    script_path = STATE_DIR / "autoupdate_child.py"
    try:
        from codewiki import __version__

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        script_path.write_text(_CHILD_SCRIPT, encoding="utf-8")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        subprocess.Popen(
            [sys.executable, str(script_path), str(STATE_FILE), PACKAGE_NAME,
             __version__, str(WAIT_FOR_EXIT_TIMEOUT)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, **kwargs,
        )
    except Exception:
        logger.debug("spawn updater failed", exc_info=True)  # fail-open


# ===================================================================
#  健康自检（Q4/Q10）：仅在升级后的首次启动跑
# ===================================================================


def _health_check_if_needed() -> None:
    state = _read_state()
    if state.get("last_result") != "upgraded":
        return
    try:
        from importlib.metadata import version as dist_version

        meta_v = dist_version(PACKAGE_NAME)
        import codewiki

        if meta_v != codewiki.__version__:
            # 半升级损坏态：重装元数据版本自愈
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--force-reinstall",
                 f"{PACKAGE_NAME}=={meta_v}"],
                capture_output=True, timeout=1800,
            )
    except Exception:
        pass  # fail-open
    finally:
        _write_state({**state, "last_result": "checked"})


# ===================================================================
#  主入口（挂载点调用，微秒级）
# ===================================================================


def maybe_self_update() -> None:
    """CLI main() / MCP server main() 启动时调用。零阻塞、fail-open。

    主进程只做：读状态文件 → 判断是否到期/合格 → 派生 detached 子进程。
    PyPI 查询与 pip 安装全部在子进程完成（Q12 全异步）。
    """
    try:
        _health_check_if_needed()
        cleanup_stale_old_files()
        if not _eligible():
            return
        state = _read_state()
        if time.time() - state.get("last_check", 0) < CHECK_INTERVAL:
            return
        lock = _UpdateLock()
        if not lock.acquire():
            return  # 别的实例正在升级
        try:
            _write_state({**state, "last_check": time.time()})
            _spawn_updater()
        finally:
            lock.release()
    except Exception:
        logger.debug("self-update skipped", exc_info=True)  # fail-open


# ===================================================================
#  前台升级（codewiki upgrade 子命令，Q9）
# ===================================================================


def check_latest() -> Optional[str]:
    """查询 PyPI 最新版本。网络失败返回 None（--check 用）。"""
    import urllib.request

    try:
        with urllib.request.urlopen(PYPI_JSON_URL, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        return data["info"]["version"]
    except Exception:
        return None


def _native_deps_changed(latest: str) -> bool:
    """比较新旧版本 requires_dist 中 tree-sitter 系列的版本约束（Q6）。"""
    import urllib.request

    try:
        with urllib.request.urlopen(PYPI_JSON_URL, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        latest_reqs = {
            r.split(";")[0].strip()
            for r in (data["info"].get("requires_dist") or [])
            if any(r.startswith(p) for p in NATIVE_DEP_PREFIXES)
        }
        from importlib.metadata import requires

        current_reqs = {
            r.split(";")[0].strip()
            for r in (requires(PACKAGE_NAME) or [])
            if any(r.startswith(p) for p in NATIVE_DEP_PREFIXES)
        }
        return latest_reqs != current_reqs
    except Exception:
        return True  # 查不到就当有风险，走保守路径


def run_foreground_upgrade() -> int:
    """`codewiki upgrade`：前台立即升级，返回退出码。"""
    import click

    from codewiki import __version__

    latest = check_latest()
    if latest is None:
        click.secho("✗ 无法查询 PyPI（网络不可达或超时）", fg="red")
        return 1
    if _parse_version(latest) == _parse_version(__version__):
        click.echo(f"已是最新版本 v{__version__}")
        return 0
    if not _auto_upgradable(__version__, latest):
        click.secho(
            f"发现新版本 v{latest}（当前 v{__version__}），但 major 版本变更需手动确认：\n"
            f"  pip install --upgrade {PACKAGE_NAME}=={latest}",
            fg="yellow",
        )
        return 0
    mode = "wait-for-exit" if _native_deps_changed(latest) else "rename-aside"
    click.echo(f"升级 v{__version__} → v{latest}（模式：{mode}）")
    lock = _UpdateLock()
    if not lock.acquire():
        click.secho("✗ 另一个升级进程正在运行", fg="red")
        return 1
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade",
             f"{PACKAGE_NAME}=={latest}"],
        )
        if r.returncode == 0:
            _write_state({"last_result": "upgraded", "last_version": latest})
            click.secho(f"✓ 已升级到 v{latest}，重启后生效", fg="green")
            return 0
        click.secho("✗ pip 升级失败，请查看上方输出", fg="red")
        return 1
    finally:
        lock.release()
