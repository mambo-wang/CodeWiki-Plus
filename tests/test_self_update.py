# -*- coding: utf-8 -*-
"""自动升级（self_update）单元测试。

设计定案见 codewiki/utils/self_update.py docstring（Q1–Q14）。
集成测试（真 wheel + 本地 index + 持锁子进程）见 test_self_update_integration.py。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from codewiki.utils import self_update
from codewiki.utils.self_update import (
    _auto_upgradable,
    _parse_version,
    _UpdateLock,
)


# ===================================================================
#  版本闸门（Q3）
# ===================================================================


class TestSemverGate:
    def test_patch_upgradable(self):
        assert _auto_upgradable("5.13.1", "5.13.2")

    def test_minor_upgradable(self):
        assert _auto_upgradable("5.13.1", "5.14.0")

    def test_major_not_upgradable(self):
        assert not _auto_upgradable("5.13.1", "6.0.0")

    def test_downgrade_not_upgradable(self):
        assert not _auto_upgradable("5.14.0", "5.13.1")

    def test_same_version_not_upgradable(self):
        assert not _auto_upgradable("5.13.1", "5.13.1")

    def test_invalid_version_rejected(self):
        assert _parse_version("not-a-version") is None
        assert not _auto_upgradable("5.13.1", "bad")

    def test_version_with_suffix_parsed(self):
        assert _parse_version("5.13.1rc1") == (5, 13, 1)


# ===================================================================
#  环境闸门（Q1/Q2）
# ===================================================================


class TestEligibility:
    def test_env_var_disables(self, monkeypatch):
        monkeypatch.setenv("CODEWIKI_NO_AUTOUPDATE", "1")
        assert self_update._autoupdate_disabled() is True

    def test_config_disables(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        (tmp_path / "config.json").write_text(
            json.dumps({"autoupdate": False}), encoding="utf-8"
        )
        assert self_update._autoupdate_disabled() is True

    def test_config_enabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        assert self_update._autoupdate_disabled() is False

    def test_pipx_env_skipped(self, monkeypatch):
        monkeypatch.setattr(self_update.sys, "prefix", "/home/u/pipx/venvs/codewiki")
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        assert self_update._managed_env() is False

    def test_uv_tool_env_skipped(self, monkeypatch):
        monkeypatch.setattr(self_update.sys, "prefix", "/home/u/.local/share/uv/tools/codewiki")
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        assert self_update._managed_env() is False

    def test_conda_env_skipped(self, monkeypatch):
        monkeypatch.setattr(self_update.sys, "prefix", "/opt/conda/envs/codewiki")
        monkeypatch.setenv("CONDA_DEFAULT_ENV", "codewiki")
        monkeypatch.delenv("PIPX_HOME", raising=False)
        assert self_update._managed_env() is False

    def test_plain_venv_allowed(self, monkeypatch):
        monkeypatch.setattr(self_update.sys, "prefix", "/home/u/proj/.venv")
        monkeypatch.delenv("PIPX_HOME", raising=False)
        monkeypatch.delenv("CONDA_DEFAULT_ENV", raising=False)
        assert self_update._managed_env() is True


# ===================================================================
#  互斥锁（Q8）
# ===================================================================


class TestUpdateLock:
    def test_acquire_release(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        lock = _UpdateLock()
        assert lock.acquire() is True
        assert lock.release() is None
        assert not (tmp_path / ".autoupdate.lock").exists()

    def test_second_acquire_fails(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        first, second = _UpdateLock(), _UpdateLock()
        assert first.acquire() is True
        assert second.acquire() is False
        first.release()

    def test_stale_lock_preempted(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        lock_file = tmp_path / ".autoupdate.lock"
        monkeypatch.setattr(self_update, "LOCK_FILE", lock_file)
        lock_file.write_text("123")
        # 把 mtime 改到超时之前
        old = time.time() - self_update.LOCK_TIMEOUT - 10
        import os

        os.utime(lock_file, (old, old))
        lock = _UpdateLock(timeout=self_update.LOCK_TIMEOUT)
        assert lock.acquire() is True  # 死锁抢占
        lock.release()


# ===================================================================
#  状态文件（Q7）
# ===================================================================


class TestStateFile:
    def test_roundtrip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        self_update._write_state({"last_check": 123, "last_result": "upgraded"})
        assert self_update._read_state() == {"last_check": 123, "last_result": "upgraded"}

    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "nope.json")
        assert self_update._read_state() == {}

    def test_corrupt_file_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "bad.json")
        (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
        assert self_update._read_state() == {}


# ===================================================================
#  maybe_self_update 主入口：fail-open + 到期检查
# ===================================================================


class TestMaybeSelfUpdate:
    def test_not_eligible_no_spawn(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        monkeypatch.setenv("CODEWIKI_NO_AUTOUPDATE", "1")
        calls = []
        monkeypatch.setattr(self_update, "_spawn_updater", lambda *a: calls.append(a))
        self_update.maybe_self_update()
        assert calls == []

    def test_recent_check_no_spawn(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        monkeypatch.delenv("CODEWIKI_NO_AUTOUPDATE", raising=False)
        monkeypatch.setattr(self_update, "_eligible", lambda: True)
        self_update._write_state({"last_check": time.time()})
        calls = []
        monkeypatch.setattr(self_update, "_spawn_updater", lambda *a: calls.append(a))
        self_update.maybe_self_update()
        assert calls == []

    def test_due_check_spawns(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        monkeypatch.delenv("CODEWIKI_NO_AUTOUPDATE", raising=False)
        monkeypatch.setattr(self_update, "_eligible", lambda: True)
        monkeypatch.setattr(self_update, "_health_check_if_needed", lambda: None)
        monkeypatch.setattr(self_update, "cleanup_stale_old_files", lambda: None)
        self_update._write_state({"last_check": time.time() - 2 * self_update.CHECK_INTERVAL})
        calls = []
        monkeypatch.setattr(self_update, "_spawn_updater", lambda: calls.append(1))
        self_update.maybe_self_update()
        assert len(calls) == 1

    def test_never_raises(self, monkeypatch, tmp_path):
        """fail-open 铁律：任何内部异常都必须被吞掉。"""
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        monkeypatch.setattr(self_update, "LOCK_FILE", tmp_path / ".autoupdate.lock")
        monkeypatch.delenv("CODEWIKI_NO_AUTOUPDATE", raising=False)
        monkeypatch.setattr(self_update, "_eligible", lambda: True)
        monkeypatch.setattr(
            self_update, "_health_check_if_needed", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        self_update.maybe_self_update()  # 不应抛出


# ===================================================================
#  健康自检（Q4/Q10）
# ===================================================================


class TestHealthCheck:
    def test_skipped_when_not_upgraded(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        self_update._write_state({"last_result": "checked"})
        calls = []
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: calls.append(a) or type("R", (), {"returncode": 0})()
        )
        self_update._health_check_if_needed()
        assert calls == []

    def test_marks_checked_after_run(self, monkeypatch, tmp_path):
        monkeypatch.setattr(self_update, "STATE_DIR", tmp_path)
        monkeypatch.setattr(self_update, "STATE_FILE", tmp_path / "autoupdate.json")
        self_update._write_state({"last_result": "upgraded"})
        monkeypatch.setattr(
            "subprocess.run", lambda *a, **kw: type("R", (), {"returncode": 0})()
        )
        self_update._health_check_if_needed()
        assert self_update._read_state()["last_result"] == "checked"
