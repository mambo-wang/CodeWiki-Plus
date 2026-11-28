"""C3 artifact facts: deterministic engineering facts outside the source graph."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import git
import pytest


def _windows_symlink_privilege() -> bool:
    """探测当前 Windows 进程是否有创建 symlink 的特权。"""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            (Path(tmp) / "link").symlink_to(target, target_is_directory=True)
            return True
    except OSError:
        return False

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.analysis import (
    _collect_artifact_facts,
    _merge_artifact_changes,
    handle_analyze_repo,
)
from codewiki.mcp.tools.artifact_facts import (
    ArtifactFactOptions,
    analyze_artifact_facts,
    artifact_facts_path,
    classify_artifact,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def artifact_repo(tmp_path: Path) -> Path:
    _write(tmp_path, "pkg/main.py", "def main():\n    return 0\n")
    _write(
        tmp_path,
        "Makefile",
        "VAR := ignored\n.PHONY: build test\n\nbuild:\n\tpython -m pkg.main\n\n"
        "test: build\n\tpython pkg/main.py\n",
    )
    _write(
        tmp_path,
        "Dockerfile",
        "FROM python:3.12 AS builder\nCOPY pkg/main.py /app/main.py\nRUN make build\n\n"
        "FROM python:3.12-slim\nCOPY --from=builder /app /app\n"
        'ENTRYPOINT ["python", "/app/main.py"]\n',
    )
    _write(
        tmp_path,
        "compose.yml",
        "services:\n  api:\n    build:\n      context: .\n      dockerfile: Dockerfile\n"
        "    ports:\n      - '8080:80'\n    environment:\n      API_TOKEN: literal-secret\n"
        "    depends_on:\n      - db\n  db:\n    image: postgres:16\n",
    )
    _write(
        tmp_path,
        "package.json",
        '{\n  "name": "demo",\n  "version": "1.0.0",\n  "scripts": {\n'
        '    "build": "node scripts/build.js",\n    "test": "npm run build"\n  }\n}\n',
    )
    _write(tmp_path, "scripts/build.js", "function build() { return 1; }\n")
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\nrequires-python = ">=3.12"\n\n'
        '[project.scripts]\ndemo = "pkg.main:main"\n',
    )
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "name: CI\non: [push]\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n      - run: make lint\n"
        "  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n",
    )
    _write(
        tmp_path,
        "api/openapi.yaml",
        "openapi: 3.1.0\ninfo:\n  title: Demo\n  version: 1.0.0\npaths:\n"
        "  /health:\n    get:\n      operationId: health\n",
    )
    _write(
        tmp_path,
        "proto/message.proto",
        'syntax = "proto3";\nservice Demo {\n  rpc Get(Request) returns (Reply);\n}\n'
        "message Request {}\nmessage Reply {}\n",
    )
    _write(tmp_path, "scripts/run.sh", "#!/bin/sh\npython -m pkg.main\n")
    _write(tmp_path, "README.md", "# demo\n")
    _write(tmp_path, "package-lock.json", '{"lockfileVersion": 3}\n')
    return tmp_path


def _facts(result: dict, path: str) -> list[dict]:
    return [fact for fact in result["facts"] if fact["path"] == path]


def _fact(result: dict, path: str, name: str) -> dict:
    matches = [fact for fact in _facts(result, path) if fact["name"] == name]
    assert len(matches) == 1, (path, name, matches)
    return matches[0]


@pytest.mark.parametrize(
    "rel_path,expected",
    [
        (".github/workflows/ci.yml", "ci"),
        (".gitlab-ci.yml", "ci"),
        ("Dockerfile", "container"),
        ("docker/Dockerfile.dev", "container"),
        ("compose.yaml", "container"),
        ("package.json", "manifest"),
        ("pyproject.toml", "manifest"),
        ("Makefile", "build"),
        ("api/openapi.yaml", "schema"),
        ("proto/msg.proto", "schema"),
        ("schemas/demo.schema.json", "schema"),
        ("scripts/run.sh", "script"),
        ("README.md", None),
        ("docs/guide.md", None),
        ("package-lock.json", None),
        ("pkg/main.py", None),
        ("node_modules/pkg/package.json", None),
        ("repowiki/schema.yaml", None),
    ],
)
def test_classify_artifact_table(rel_path: str, expected: str | None) -> None:
    assert classify_artifact(rel_path) == expected


def test_collects_core_facts_with_traceable_lines_and_references(artifact_repo: Path) -> None:
    result = analyze_artifact_facts(artifact_repo)

    assert result["status"] == "ok"
    assert result["changed_files"] == []
    assert result["summary"]["files_failed"] == 0
    assert result["summary"]["facts"] == len(result["facts"])
    assert _fact(result, "Makefile", "build")["line"] == 4
    assert _fact(result, "Makefile", "build")["attributes"]["prerequisites"] == []
    assert _fact(result, "Makefile", "test")["attributes"]["prerequisites"] == ["build"]
    assert {"kind": "module", "value": "pkg.main"} in _fact(result, "Makefile", "build")[
        "references"
    ]
    assert _fact(result, "Dockerfile", "builder")["attributes"]["base_image"] == "python:3.12"
    assert _fact(result, "Dockerfile", "stage_1")["line"] == 5
    assert _fact(result, "compose.yml", "api")["attributes"]["depends_on"] == ["db"]
    assert _fact(result, "compose.yml", "api")["attributes"]["ports"] == ["8080:80"]
    assert _fact(result, "package.json", "build")["line"] == 5
    assert _fact(result, "pyproject.toml", "demo")["attributes"]["target"] == "pkg.main:main"
    assert (
        _fact(result, ".github/workflows/ci.yml", "lint")["attributes"]["runner"] == "ubuntu-latest"
    )
    assert _fact(result, ".github/workflows/ci.yml", "lint")["attributes"]["step_count"] == 2
    assert _fact(result, "api/openapi.yaml", "GET /health")["line"] == 7
    assert _fact(result, "proto/message.proto", "Demo")["attributes"]["unit_type"] == "service"
    assert _fact(result, "scripts/run.sh", "run.sh")["attributes"]["interpreter"] == "/bin/sh"
    assert not any(fact["path"] in {"README.md", "package-lock.json"} for fact in result["facts"])
    assert all(fact["id"].startswith("artifact:") for fact in result["facts"])
    assert len({fact["id"] for fact in result["facts"]}) == len(result["facts"])


def test_sensitive_environment_values_and_command_bodies_are_not_exported(
    artifact_repo: Path,
) -> None:
    _write(artifact_repo, "scripts/opaque", "#!/usr/bin/env sh -c literal-secret\n")
    result = analyze_artifact_facts(artifact_repo)
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert "literal-secret" not in serialized
    assert "node scripts/build.js" not in serialized
    assert "python -m pkg.main" not in serialized
    assert "API_TOKEN" not in serialized


def test_malformed_files_degrade_to_partial_without_losing_valid_facts(artifact_repo: Path) -> None:
    _write(artifact_repo, ".github/workflows/broken.yml", "jobs:\n  bad: [\n")
    _write(artifact_repo, "broken/package.json", '{"name": ')

    result = analyze_artifact_facts(artifact_repo)

    assert result["status"] == "partial"
    failed = {item["path"]: item for item in result["files"] if item["status"] == "failed"}
    assert set(failed) == {".github/workflows/broken.yml", "broken/package.json"}
    assert failed[".github/workflows/broken.yml"]["error"]["code"] == "invalid_yaml"
    assert failed["broken/package.json"]["error"]["code"] == "invalid_json"
    assert result["warnings"]
    assert _fact(result, "Makefile", "build")["name"] == "build"


def test_caps_truncation_and_omissions_are_explicit(artifact_repo: Path) -> None:
    result = analyze_artifact_facts(
        artifact_repo,
        options=ArtifactFactOptions(max_files=4, max_units_per_file=1),
    )

    assert result["status"] == "partial"
    assert result["limits"]["max_files"] == 4
    assert result["summary"]["files_parsed"] == 4
    assert result["omitted_files"]
    assert all(item["reason"] == "file_cap" for item in result["omitted_files"])
    assert any("unit_cap" in warning for warning in result["warnings"])

    truncated = analyze_artifact_facts(
        artifact_repo,
        options=ArtifactFactOptions(max_files=1, max_file_bytes=80),
    )
    assert any(item.get("truncated") for item in truncated["files"])
    assert truncated["summary"]["files_truncated"] == 1


def test_changed_files_include_added_modified_and_deleted_artifacts(artifact_repo: Path) -> None:
    first = analyze_artifact_facts(artifact_repo)
    _write(artifact_repo, "Dockerfile", "FROM alpine:3.20\n")
    (artifact_repo / "scripts/run.sh").unlink()
    _write(artifact_repo, "new/compose.yml", "services:\n  web:\n    image: nginx:alpine\n")

    second = analyze_artifact_facts(artifact_repo, previous=first)

    assert second["changed_files"] == ["Dockerfile", "new/compose.yml", "scripts/run.sh"]
    assert first["changed_files"] == []
    assert second["fingerprints"] != first["fingerprints"]


def test_repeated_collection_is_byte_deterministic(artifact_repo: Path) -> None:
    first = analyze_artifact_facts(artifact_repo)
    second = analyze_artifact_facts(artifact_repo)

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_include_and_exclude_patterns_apply_to_artifacts(artifact_repo: Path) -> None:
    included = analyze_artifact_facts(
        artifact_repo, options=ArtifactFactOptions(include_patterns=("*.yml",))
    )
    excluded = analyze_artifact_facts(
        artifact_repo, options=ArtifactFactOptions(exclude_patterns=("docker/*", ".github/*"))
    )

    assert included["facts"]
    assert all(fact["path"].endswith((".yml", ".yaml")) for fact in included["facts"])
    assert not any(fact["path"].startswith((".github/", "docker/")) for fact in excluded["facts"])


def test_toml_entry_lines_stay_within_their_section(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "demo"\n\n[project.scripts]\nfirst = "pkg.first:main"\n'
        'second = "pkg.second:main"\n\n[tool.poetry.scripts]\nfirst = "pkg.other:main"\n',
    )

    result = analyze_artifact_facts(tmp_path)
    matches = _facts(result, "pyproject.toml")

    assert [(fact["name"], fact["line"]) for fact in matches] == [
        ("pyproject.toml", 1),
        ("first", 5),
        ("second", 6),
        ("first", 9),
    ]


def test_make_inline_and_expanded_recipes_do_not_leak(artifact_repo: Path) -> None:
    _write(
        artifact_repo,
        "Makefile",
        "leaky: ; echo SECRET-INLINE\nexpanded: $(shell echo SECRET-EXPANDED)\n",
    )

    result = analyze_artifact_facts(artifact_repo)
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert "SECRET-INLINE" not in serialized
    assert "SECRET-EXPANDED" not in serialized
    assert _fact(result, "Makefile", "leaky")["attributes"]["inline_recipe"] is True
    assert _fact(result, "Makefile", "expanded")["attributes"]["prerequisites"] == []
    assert _fact(result, "Makefile", "expanded")["attributes"]["prerequisites_omitted"] == 3


def test_path_references_handle_posix_and_windows_separators(artifact_repo: Path) -> None:
    _write(
        artifact_repo, "scripts/paths.sh", "#!/bin/sh\npython pkg/main.py\npython pkg\\main.py\n"
    )

    result = analyze_artifact_facts(artifact_repo)
    refs = _fact(result, "scripts/paths.sh", "paths.sh")["references"]

    assert {"kind": "path", "value": "pkg/main.py"} in refs
    assert refs.count({"kind": "path", "value": "pkg/main.py"}) == 1


def test_fingerprint_detects_same_size_edits_beyond_parse_cap(tmp_path: Path) -> None:
    _write(tmp_path, "package.json", '{"name":"aa"}')
    options = ArtifactFactOptions(max_file_bytes=10)
    first = analyze_artifact_facts(tmp_path, options=options)
    _write(tmp_path, "package.json", '{"name":"bb"}')
    second = analyze_artifact_facts(tmp_path, previous=first, options=options)

    assert first["fingerprints"] != second["fingerprints"]
    assert second["changed_files"] == ["package.json"]


def test_ci_provider_shapes_are_parsed_or_explicitly_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".gitlab-ci.yml",
        "stages: [test]\nbuild:\n  stage: test\n  script:\n    - python pkg/main.py\n",
    )
    _write(tmp_path, ".buildkite/pipeline.yml", "steps:\n  - label: test\n    command: make test\n")
    _write(
        tmp_path,
        ".github/actions/demo/action.yml",
        "name: demo\ninputs:\n  who:\n    description: target\nruns:\n  using: composite\n  steps:\n    - run: make test\n",
    )
    result = analyze_artifact_facts(tmp_path)

    assert _fact(result, ".gitlab-ci.yml", "build")["attributes"]["ci_type"] == "gitlab"
    assert _fact(result, ".gitlab-ci.yml", "build")["line"] == 2
    assert (
        _fact(result, ".buildkite/pipeline.yml", "pipeline.yml")["attributes"]["ci_type"]
        == "buildkite"
    )
    action = _fact(result, ".github/actions/demo/action.yml", "action.yml")
    assert action["attributes"]["ci_type"] == "github_action"
    assert action["attributes"]["structure_recognized"] is True
    assert "python pkg/main.py" not in json.dumps(result, ensure_ascii=False)

    _write(tmp_path, ".gitlab-ci.yml", "unrecognized: scalar\n")
    invalid = analyze_artifact_facts(tmp_path)
    failed = next(item for item in invalid["files"] if item["path"] == ".gitlab-ci.yml")
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "unsupported_ci_structure"


@pytest.mark.skipif(
    sys.platform == "win32" and not _windows_symlink_privilege(),
    reason="Windows 无特权模式无法创建 symlink（WinError 1314）",
)


def test_symlinks_nested_repos_and_gitignored_artifacts_are_excluded(artifact_repo: Path) -> None:
    _write(artifact_repo, ".gitignore", "ignored/\n")
    _write(artifact_repo, "ignored/Makefile", "bad:\n\ttrue\n")
    _write(artifact_repo, "nested/Makefile", "bad:\n\ttrue\n")
    (artifact_repo / "nested" / ".git").mkdir()
    (artifact_repo / "linked").symlink_to(artifact_repo, target_is_directory=True)
    try:
        (artifact_repo / "Dockerfile.link").symlink_to(artifact_repo / "Dockerfile")
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = analyze_artifact_facts(artifact_repo)
    paths = {fact["path"] for fact in result["facts"]}

    assert not any(path.startswith(("ignored/", "nested/", "linked/")) for path in paths)
    assert "Dockerfile.link" not in paths


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_non_regular_artifact_is_reported_without_blocking(artifact_repo: Path) -> None:
    pipe = artifact_repo / "pipe" / "Dockerfile"
    pipe.parent.mkdir()
    os.mkfifo(pipe)

    result = analyze_artifact_facts(artifact_repo)
    failed = next(item for item in result["files"] if item["path"] == "pipe/Dockerfile")

    assert result["status"] == "partial"
    assert failed["status"] == "failed"
    assert failed["error"]["code"] == "unreadable"


def test_artifact_index_is_registered_as_rebuildable() -> None:
    from codewiki.src.config import TEAM_LAYOUT_REBUILDABLE_FILES

    assert ".meta/artifact_facts.json" in TEAM_LAYOUT_REBUILDABLE_FILES
    template = (
        Path(__file__).resolve().parents[1]
        / "codewiki"
        / "templates"
        / "workspace"
        / "gitignore.tpl"
    )
    assert "repowiki/.meta/artifact_facts.json" in template.read_text(encoding="utf-8")


def test_collection_failure_is_explicit_and_does_not_block_source_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path, "a.py", "def func_a():\n    return 1\n")
    _write(tmp_path, "Dockerfile", "FROM alpine:3.20\n")
    monkeypatch.setattr(
        "codewiki.mcp.tools.artifact_facts.analyze_artifact_facts",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, SessionStore())
    )

    assert "error" not in response, response
    assert response["artifact_facts"]["status"] == "unavailable"
    assert response["artifact_facts"]["warnings"] == ["collection_failed:RuntimeError"]
    assert response["stats"]["total_components"] >= 1


def test_persistence_failure_keeps_valid_facts_and_marks_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path, "Dockerfile", "FROM alpine:3.20\n")
    monkeypatch.setattr(
        "codewiki.src.store.atomic_write",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk-full")),
    )

    result = _collect_artifact_facts(
        tmp_path, tmp_path / "repowiki", include_patterns=None, exclude_patterns=None
    )

    assert result["status"] == "partial"
    assert result["facts"]
    assert "persist_failed:RuntimeError" in result["warnings"]


def test_corrupt_previous_index_is_visible_and_forces_full_artifact_diff(tmp_path: Path) -> None:
    _write(tmp_path, "Dockerfile", "FROM alpine:3.20\n")
    output = tmp_path / "repowiki"
    first = _collect_artifact_facts(tmp_path, output, include_patterns=None, exclude_patterns=None)
    assert first["status"] == "ok"
    artifact_facts_path(tmp_path, output).write_text("{broken", encoding="utf-8")

    second = _collect_artifact_facts(tmp_path, output, include_patterns=None, exclude_patterns=None)

    assert second["status"] == "partial"
    assert "previous_index_unreadable" in second["warnings"]
    assert second["changed_files"] == ["Dockerfile"]


def test_artifact_only_diff_survives_missing_source_change_baseline() -> None:
    changes = _merge_artifact_changes(None, {"changed_files": ["Dockerfile"]})

    assert changes is not None
    assert changes["changed_files"] == ["Dockerfile"]
    assert changes["artifact_changed_files"] == ["Dockerfile"]
    assert changes["no_changes"] is False


def test_centralized_artifact_path_is_isolated_per_member(tmp_path: Path) -> None:
    from codewiki.mcp.tools import workspace_bootstrap as wb
    from codewiki.mcp.tools import workspace_layout as wl

    wl.clear_cache()
    try:
        workspace = tmp_path / "workspace"
        repo = workspace / "a"
        repo.mkdir(parents=True)
        initialized = json.loads(
            wb.handle_init_workspace({"workspace_path": str(workspace), "layout": "centralized"})
        )
        registered = json.loads(
            wb.handle_add_workspace_repo(
                {
                    "workspace_path": str(workspace),
                    "url": "https://example.com/a.git",
                    "clone": False,
                }
            )
        )
        assert initialized["status"] == "ok", initialized
        assert registered["status"] == "ok", registered
        output = wl.default_output_dir(repo)

        assert (
            artifact_facts_path(repo, output)
            == workspace / ".codewiki" / "a" / "artifact_facts.json"
        )
    finally:
        wl.clear_cache()


def test_analyze_repo_exposes_facts_and_detects_artifact_only_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write(tmp_path, "a.py", "def func_a():\n    return 1\n")
    _write(tmp_path, "Dockerfile", "FROM python:3.12\n")
    repo = git.Repo.init(tmp_path)
    repo.git.config("user.name", "test")
    repo.git.config("user.email", "test@example.com")
    repo.index.add(["a.py", "Dockerfile"])
    repo.index.commit("initial")
    store = SessionStore()

    first = json.loads(
        handle_analyze_repo({"repo_path": str(tmp_path), "incremental": False}, store)
    )
    assert "error" not in first, first
    assert first["artifact_facts"]["status"] == "ok"
    assert first["files"]["artifact_facts"].endswith("repowiki/.meta/artifact_facts.json")
    before_ids = set(store.get_cache(str(tmp_path)).get_all_metas())
    assert not any(component_id.startswith("artifact:") for component_id in before_ids)

    _write(tmp_path, "Dockerfile", "FROM python:3.12 AS runtime\n")
    monkeypatch.setattr(
        "codewiki.mcp.cache.AnalysisCache.detect_changes",
        lambda self: {"changed_files": [], "method": "git", "no_changes": True},
    )
    second = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in second, second
    assert second["changes"]["no_changes"] is False
    assert second["changes"]["changed_files"] == ["Dockerfile"]
    assert second["changes"]["artifact_changed_files"] == ["Dockerfile"]
    assert _fact(second["artifact_facts"], "Dockerfile", "runtime")["name"] == "runtime"
    after_ids = set(store.get_cache(str(tmp_path)).get_all_metas())
    assert after_ids == before_ids

    monkeypatch.setattr(
        "codewiki.mcp.cache.AnalysisCache.detect_changes",
        lambda self: {"changed_files": [], "method": "git", "no_changes": True},
    )
    third = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in third, third
    assert third["changes"]["no_changes"] is True
    assert third["artifact_facts"]["changed_files"] == []
    assert third["files"]["artifact_facts"].endswith("repowiki/.meta/artifact_facts.json")
    assert artifact_facts_path(tmp_path, tmp_path / "repowiki").is_file()

    monkeypatch.setattr(
        "codewiki.mcp.tools.artifact_facts.analyze_artifact_facts",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    fourth = json.loads(handle_analyze_repo({"repo_path": str(tmp_path)}, store))
    assert "error" not in fourth, fourth
    assert fourth["changes"]["no_changes"] is True
    assert fourth["artifact_facts"]["status"] == "unavailable"
    assert "partial or unavailable" in fourth["hint"]
