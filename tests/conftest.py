"""Shared pytest fixtures for MCP tool tests.

``analyzed_repo`` builds a small temp git repo (a.py → b.py → c.py plus a
tests/ dir) and runs the real analyze_repo pipeline into a fresh
:class:`SessionStore`, returning ``(tmp_path, store)``.
"""

from __future__ import annotations

import json

import git
import pytest

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import handle_analyze_repo

PY_A = '''"""module a"""\ndef func_a():\n    return 1\n'''

PY_B = '''"""module b"""\nimport a\n\ndef func_b():\n    return a.func_a()\n\ndef func_other():\n    return 42\n'''

PY_C = '''"""module c"""\nimport b\n\ndef func_c():\n    return b.func_b()\n'''

PY_C_TEST = '''"""tests for c"""\nimport c\n\ndef test_func_c():\n    assert c.func_c() == 1\n'''


@pytest.fixture()
def analyzed_repo(tmp_path):
    """A temp git repo with a.py/b.py/c.py analyzed into a CodeWiki session."""
    (tmp_path / "a.py").write_text(PY_A, encoding="utf-8")
    (tmp_path / "b.py").write_text(PY_B, encoding="utf-8")
    (tmp_path / "c.py").write_text(PY_C, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_c.py").write_text(PY_C_TEST, encoding="utf-8")

    repo = git.Repo.init(str(tmp_path))
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    # NOTE: index.add(".") is broken on GitPython 3.1.50 Windows — it walks
    # into .git/ and stages paths like "./a.py" (prefix). Add explicit paths.
    repo.index.add(["a.py", "b.py", "c.py", "tests/test_c.py"])
    repo.index.commit("initial")

    store = SessionStore()
    resp = json.loads(
        handle_analyze_repo(
            {"repo_path": str(tmp_path), "output_dir": str(tmp_path / "repowiki"), "incremental": False},
            store,
        )
    )
    assert "error" not in resp, resp
    return tmp_path, store
