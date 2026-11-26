"""运行边界回归：Git stdin、Mermaid 三态与嵌套仓库遍历。"""

import asyncio
import os
import subprocess
from datetime import datetime
from types import SimpleNamespace

import pytest

from codewiki.cli.commands import backfill_note_authors
from codewiki.mcp.tools import note_query, workspace_bootstrap
from codewiki.src.be import utils
from codewiki.src.be.dependency_analyzer.analysis import cloning, repo_analyzer
from codewiki.src.fe.github_processor import GitHubRepoProcessor


def _completed(stdout=""):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_git_config_subprocess_closes_stdin(monkeypatch):
    from codewiki.src import config

    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed("tester")

    monkeypatch.setattr(subprocess, "run", run)
    assert config._git_config_value("user.name", "/repo") == "tester"
    assert calls[0]["stdin"] is subprocess.DEVNULL


def test_git_log_subprocess_closes_stdin(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed("2026-11-26T12:00:00+00:00")

    monkeypatch.setattr(subprocess, "run", run)
    result = note_query._last_commit_time(tmp_path / "note.md", tmp_path)
    assert result == datetime.fromisoformat("2026-11-26T12:00:00+00:00")
    assert calls[0]["stdin"] is subprocess.DEVNULL


def test_workspace_clone_subprocess_closes_stdin(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed()

    monkeypatch.setattr(subprocess, "run", run)
    result = workspace_bootstrap._clone_repo(tmp_path, "dependency", "https://example.invalid/repo", 5)
    assert result["status"] == "ok"
    assert calls[0]["stdin"] is subprocess.DEVNULL


def test_backfill_git_subprocess_closes_stdin(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed("Author")

    monkeypatch.setattr(subprocess, "run", run)
    assert backfill_note_authors._git_creator_author(tmp_path, "note.md") == "Author"
    assert calls[0]["stdin"] is subprocess.DEVNULL


@pytest.mark.parametrize("commit_id", [None, "abc123"])
def test_github_processor_git_subprocesses_close_stdin(tmp_path, monkeypatch, commit_id):
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed()

    monkeypatch.setattr(subprocess, "run", run)
    assert GitHubRepoProcessor.clone_repository(
        "https://example.invalid/repo.git", str(tmp_path / "repo"), commit_id
    )
    assert len(calls) == (2 if commit_id else 1)
    assert all(call["stdin"] is subprocess.DEVNULL for call in calls)


def test_clone_repository_git_subprocesses_close_stdin(tmp_path, monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(kwargs)
        return _completed()

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(cloning.tempfile, "mkdtemp", lambda prefix: str(tmp_path))
    monkeypatch.setattr(cloning, "GIT_EXECUTABLE_PATH", "git")
    monkeypatch.setattr(cloning, "os", SimpleNamespace(name="nt", path=os.path, makedirs=os.makedirs))

    assert cloning.clone_repository("owner/repo") == str(tmp_path)
    assert len(calls) == 4
    assert all(call["stdin"] is subprocess.DEVNULL for call in calls)


@pytest.mark.asyncio
async def test_mermaid_remote_worker_is_daemon(monkeypatch):
    threads = []

    class FakeThread:
        def __init__(self, *, target, daemon):
            self.target = target
            self.daemon = daemon
            threads.append(self)

        def start(self):
            pass

    monkeypatch.setattr(utils.threading, "Thread", FakeThread)
    future = utils._run_in_daemon_thread(lambda: "done")
    assert threads[0].daemon is True
    future.cancel()


@pytest.mark.asyncio
async def test_disabled_mermaid_validation_is_unavailable(monkeypatch):
    async def no_local(_):
        return None

    monkeypatch.setattr(utils, "_try_pythonmonkey_parse", no_local)
    monkeypatch.setattr(utils, "_MERMAID_PY_BROKEN", True)
    result = await utils.validate_single_diagram("flowchart TD\nA-->B", 1, 1)
    assert "validation unavailable" in result
    assert "syntax errors" not in result


@pytest.mark.asyncio
async def test_timed_out_mermaid_validation_is_unavailable(monkeypatch):
    async def no_local(_):
        return None

    async def no_remote(_):
        return ""

    async def timeout(*args, **kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(utils, "_try_pythonmonkey_parse", no_local)
    monkeypatch.setattr(utils.asyncio, "to_thread", no_remote)
    monkeypatch.setattr(utils.asyncio, "wait_for", timeout)
    monkeypatch.setattr(utils, "_MERMAID_PY_BROKEN", False)
    result = await utils.validate_single_diagram("flowchart TD\nA-->B", 1, 1)
    assert "validation unavailable" in result
    assert utils._MERMAID_PY_BROKEN is True


@pytest.mark.asyncio
async def test_mermaid_file_report_distinguishes_invalid_and_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "mixed.md"
    path.write_text(
        "```mermaid\nflowchart TD\nA-->B\n```\n```mermaid\nflowchart TD\nC-->D\n```\n",
        encoding="utf-8",
    )
    results = iter(
        [
            SimpleNamespace(status="unavailable", message="offline"),
            SimpleNamespace(status="invalid", message="Parse error on line 1"),
        ]
    )

    async def validate(_):
        return next(results)

    monkeypatch.setattr(utils, "_validate_diagram", validate, raising=False)
    report = await utils.validate_mermaid_diagrams(str(path), "mixed.md")
    assert "syntax errors" in report
    assert "unavailable" in report
    assert "are syntax correct" not in report


@pytest.mark.asyncio
async def test_unavailable_mermaid_diagram_is_not_claimed_valid(tmp_path, monkeypatch):
    path = tmp_path / "offline.md"
    path.write_text("```mermaid\nflowchart TD\nA-->B\n```\n", encoding="utf-8")

    async def validate(_):
        return SimpleNamespace(status="unavailable", message="offline")

    monkeypatch.setattr(utils, "_validate_diagram", validate, raising=False)
    report = await utils.validate_mermaid_diagrams(str(path), "offline.md")
    assert "unavailable" in report
    assert "syntax errors" not in report
    assert "syntax correct" not in report


def test_doc_writer_mermaid_error_marker_requires_invalid_report_prefix():
    from codewiki.mcp.tools.doc_writer import _has_mermaid_syntax_errors

    assert _has_mermaid_syntax_errors("Mermaid syntax errors found in file: page.md\nDiagram 1: bad")
    assert not _has_mermaid_syntax_errors("Mermaid validation unavailable for file: page.md\nHTTP 503")
    assert not _has_mermaid_syntax_errors("All mermaid diagrams in file: page.md are syntax correct")


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (200, "<svg></svg>", "valid"),
        (400, "Parse error on line 2: got 'PS'", "invalid"),
        (503, "service unavailable", "unavailable"),
        (400, "Bad parameters", "unavailable"),
    ],
)
def test_mermaid_remote_adapter_classifies_responses(monkeypatch, status_code, body, expected):
    import mermaid as md  # type: ignore[import-untyped]

    response = SimpleNamespace(status_code=status_code, text=body)
    if 200 <= status_code < 300:
        monkeypatch.setattr(md, "Mermaid", lambda _: SimpleNamespace(svg_response=response))
    else:
        error = md.MermaidError(status_code, body, "https://example.invalid")
        monkeypatch.setattr(md, "Mermaid", lambda _: (_ for _ in ()).throw(error))
    assert utils._parse_via_mermaid_py("flowchart TD\nA-->B").status == expected


def _git_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()


def _nested_repo(tmp_path):
    repo = tmp_path / "repo"
    _git_dir(repo)
    (repo / ".gitmodules").write_text(
        '[submodule "dependency"]\n\tpath = vendor/declared\n\turl = https://example.invalid/dependency\n',
        encoding="utf-8",
    )
    (repo / "app.py").write_text("def app(): pass\n", encoding="utf-8")
    for relative in ("vendor/declared", "vendor/undeclared", ".worktrees/feature"):
        _git_dir(repo / relative)
        (repo / relative / "sentinel.py").write_text(
            "def nested_checkout_sentinel(): pass\n", encoding="utf-8"
        )
    return repo


def test_repository_tree_keeps_only_declared_nested_checkouts(tmp_path):
    repo = _nested_repo(tmp_path)
    result = repo_analyzer.RepoAnalyzer(include_patterns=["*.py"], use_gitignore=False)
    tree = result.analyze_repository_structure(str(repo))["file_tree"]
    paths = set()

    def visit(node):
        if node["type"] == "file":
            paths.add(node["path"].replace("\\", "/"))
        for child in node.get("children", []):
            visit(child)

    visit(tree)
    assert paths == {"app.py", "vendor/declared/sentinel.py"}


def test_fallback_gitignore_does_not_cross_nested_checkout_boundary(tmp_path, monkeypatch):
    repo = _nested_repo(tmp_path)
    (repo / ".gitignore").write_text("root_ignored.py\n", encoding="utf-8")
    (repo / "vendor" / "declared" / ".gitignore").write_text("*.py\n", encoding="utf-8")
    (repo / "vendor" / "undeclared" / ".gitignore").write_text("*\n", encoding="utf-8")
    monkeypatch.setattr(repo_analyzer.shutil, "which", lambda _: None)

    analyzer = repo_analyzer.RepoAnalyzer(include_patterns=["*.py"])
    analyzer.analyze_repository_structure(str(repo))
    ignore_filter = analyzer._gitignore_filter
    assert {base for base, _ in ignore_filter._fallback_specs} == {"", "vendor/declared"}
    assert ignore_filter.is_ignored("vendor/declared/sentinel.py", False)
    assert not ignore_filter.is_ignored("app.py", False)


def test_escaping_submodule_declaration_is_rejected(tmp_path):
    repo = _nested_repo(tmp_path)
    with (repo / ".gitmodules").open("a", encoding="utf-8") as stream:
        stream.write('[submodule "escape"]\n\tpath = ../outside\n')
    boundaries = repo_analyzer.RepositoryBoundaryFilter(repo)
    assert (tmp_path / "outside").resolve() not in boundaries._declared_submodules(repo.resolve())
