"""P1-2 of ADR-0020: two generation holes.

1. ``overview.md`` used to short-circuit every module agent. The skip unit is
   now the page: a missing ``<module>.md`` is regenerated even when the
   repository overview already exists.
2. A module exception used to be swallowed with ``continue`` and the run still
   exited 0. Failures are now aggregated into :class:`ModuleGenerationError`
   after every module has had its attempt, and mirrored into an existing job
   ledger as ``degraded``.

The legacy pipeline never *creates* the ledger (MCP owns it), so these tests
also pin down that a plain run with no job leaves no ``job.json`` behind.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from codewiki.mcp.tools import job_state as js
from codewiki.src.be.backend import LLMBackend, module_page_present
from codewiki.src.be.documentation_generator import (
    DocumentationGenerator,
    ModuleGenerationError,
)
from codewiki.src.config import Config


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    docs = tmp_path / "repowiki"
    (docs / ".meta").mkdir(parents=True)
    return repo, docs


def _config(tmp_path: Path, repo: Path, docs: Path) -> Config:
    return Config(
        repo_path=str(repo),
        output_dir=str(docs),
        dependency_graph_dir=str(tmp_path / "deps"),
        docs_dir=str(docs),
        max_depth=3,
        llm_base_url="http://localhost:1",
        llm_api_key="test",
        main_model="test-model",
        cluster_model="test-model",
    )


def _seed_trees(docs: Path, tree: dict) -> None:
    for name in ("module_tree.json", "first_module_tree.json"):
        (docs / ".meta" / name).write_text(json.dumps(tree), encoding="utf-8")


class FakeBackend(LLMBackend):
    """Records agent calls; can fail named modules or write nothing at all."""

    def __init__(self, failing: tuple[str, ...] = (), write_pages: bool = True):
        self.failing = set(failing)
        self.write_pages = write_pages
        self.calls: list[tuple[tuple[str, ...], str]] = []
        self.completions = 0

    def complete(self, prompt: str, *, model=None, temperature: float = 0.0) -> str:
        self.completions += 1
        return "<OVERVIEW>\n# Repository overview\n</OVERVIEW>"

    async def run_module_agent(
        self,
        module_name: str,
        components: dict,
        core_component_ids: list,
        module_path: list,
        working_dir: str,
    ) -> dict:
        self.calls.append((tuple(module_path), module_name))
        if module_name in self.failing:
            raise RuntimeError(f"boom:{module_name}")
        if self.write_pages:
            Path(working_dir, f"{module_name}.md").write_text(
                f"# {module_name}\n", encoding="utf-8"
            )
        return {}


def _leaf(name: str) -> dict:
    return {"components": [f"{name.lower()}.py"], "children": {}}


# --- hole 1: the skip unit is the page, not the run -------------------------


def test_module_page_present_ignores_overview(tmp_path):
    _, docs = _paths(tmp_path)
    (docs / "overview.md").write_text("# overview", encoding="utf-8")

    assert module_page_present(str(docs), "Auth") is False

    (docs / "Auth.md").write_text("# Auth", encoding="utf-8")
    assert module_page_present(str(docs), "Auth") is True


def test_missing_module_page_is_regenerated_when_overview_exists(tmp_path):
    repo, docs = _paths(tmp_path)
    (docs / "overview.md").write_text("# overview", encoding="utf-8")
    _seed_trees(docs, {"Auth": _leaf("Auth")})

    fake = FakeBackend()
    generator = DocumentationGenerator(_config(tmp_path, repo, docs), backend=fake)
    asyncio.run(generator.generate_module_documentation({}, ["auth.py"]))

    assert fake.calls == [(("Auth",), "Auth")]
    assert (docs / "Auth.md").is_file()
    # overview.md itself is still skipped: page-level, not run-level.
    assert fake.completions == 0


def test_parent_page_is_generated_when_overview_exists(tmp_path):
    repo, docs = _paths(tmp_path)
    (docs / "overview.md").write_text("# overview", encoding="utf-8")
    tree = {
        "Core": {
            "components": ["core.py"],
            "children": {"Leaf": _leaf("Leaf")},
        }
    }
    _seed_trees(docs, tree)

    fake = FakeBackend()
    generator = DocumentationGenerator(_config(tmp_path, repo, docs), backend=fake)
    asyncio.run(generator.generate_module_documentation({}, ["leaf.py"]))

    # Leaf page from the agent, parent page from a completion — neither is
    # blocked by the existing overview.
    assert (docs / "Leaf.md").is_file()
    assert (docs / "Core.md").is_file()
    assert fake.completions == 1


# --- hole 2: module failures surface ---------------------------------------


def test_failed_module_raises_after_the_rest_run(tmp_path):
    repo, docs = _paths(tmp_path)
    _seed_trees(docs, {"A": _leaf("A"), "B": _leaf("B")})

    fake = FakeBackend(failing=("B",))
    generator = DocumentationGenerator(_config(tmp_path, repo, docs), backend=fake)

    with pytest.raises(ModuleGenerationError) as excinfo:
        asyncio.run(generator.generate_module_documentation({}, []))

    assert excinfo.value.failures == [("B", "boom:B")]
    assert [name for _, name in fake.calls] == ["A", "B"]
    # Partial output survives, and the overview still gets generated.
    assert (docs / "A.md").is_file()
    assert (docs / "overview.md").is_file()


def test_run_writes_metadata_before_propagating_failure(tmp_path, monkeypatch):
    repo, docs = _paths(tmp_path)
    _seed_trees(docs, {"A": _leaf("A"), "B": _leaf("B")})

    generator = DocumentationGenerator(
        _config(tmp_path, repo, docs), backend=FakeBackend(failing=("B",))
    )
    monkeypatch.setattr(
        generator.graph_builder, "build_dependency_graph", lambda *a, **kw: ({}, [], [])
    )

    with pytest.raises(ModuleGenerationError):
        asyncio.run(generator.run())

    assert (docs / ".meta" / "metadata.json").is_file()


def test_plain_run_does_not_create_a_ledger(tmp_path):
    repo, docs = _paths(tmp_path)
    _seed_trees(docs, {"A": _leaf("A")})

    generator = DocumentationGenerator(_config(tmp_path, repo, docs), backend=FakeBackend())
    asyncio.run(generator.generate_module_documentation({}, []))

    assert js.job_path(repo, docs).exists() is False


# --- ledger mirroring (only when a job already exists) ---------------------


def test_failure_marks_existing_job_degraded(tmp_path):
    repo, docs = _paths(tmp_path)
    js.start_job(repo, docs, base_commit=None)
    js.record_planned(repo, docs, ["A", "B", "overview"])
    _seed_trees(docs, {"A": _leaf("A"), "B": _leaf("B")})

    generator = DocumentationGenerator(
        _config(tmp_path, repo, docs), backend=FakeBackend(failing=("B",))
    )
    with pytest.raises(ModuleGenerationError):
        asyncio.run(generator.generate_module_documentation({}, []))

    job = js.load_job(repo, docs)
    assert job is not None
    assert job["phase"] == "degraded"
    assert [entry["code"] for entry in job["degraded"]] == ["module_failed"]
    assert "B" in job["degraded"][0]["detail"]
    # A was written, overview was written, B stayed missing.
    assert js.missing_pages(job) == ["B"]


def test_silent_agent_keeps_page_missing_in_ledger(tmp_path):
    repo, docs = _paths(tmp_path)
    js.start_job(repo, docs, base_commit=None)
    js.record_planned(repo, docs, ["A", "overview"])
    _seed_trees(docs, {"A": _leaf("A")})

    generator = DocumentationGenerator(
        _config(tmp_path, repo, docs), backend=FakeBackend(write_pages=False)
    )
    asyncio.run(generator.generate_module_documentation({}, []))

    job = js.load_job(repo, docs)
    assert job is not None
    assert js.missing_pages(job) == ["A"]
    assert job["phase"] == "generating"


# --- backends no longer early-return on overview ---------------------------


def test_pydantic_backend_runs_agent_despite_overview(tmp_path, monkeypatch):
    from codewiki.src.be import pydantic_ai_backend

    repo, docs = _paths(tmp_path)
    (docs / "overview.md").write_text("# overview", encoding="utf-8")
    (docs / ".meta" / "module_tree.json").write_text("{}", encoding="utf-8")

    class MarkerError(RuntimeError):
        pass

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self, *args, **kwargs):
            raise MarkerError("agent ran")

    monkeypatch.setattr(pydantic_ai_backend, "Agent", FakeAgent)

    cfg = _config(tmp_path, repo, docs)
    backend = object.__new__(pydantic_ai_backend.PydanticAIBackend)
    backend._config = cfg
    backend._custom_instructions = ""
    backend._fallback_models = None  # FakeAgent ignores the model handle

    with pytest.raises(MarkerError):
        asyncio.run(backend.run_module_agent("Auth", {}, [], ["Auth"], str(docs)))
