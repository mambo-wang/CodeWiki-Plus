"""Generation job ledger (ADR-0020 decision 1-2) — ``.meta/job.json``.

Covers: create/resume/rebuild tiers, planned/written counters, the degraded
vs done split, fail-open reads on corrupt ledgers, and atomic writes.
"""

from __future__ import annotations

import json

from codewiki.mcp.tools import job_state as js


def _paths(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output = tmp_path / "repowiki"
    output.mkdir()
    return repo, output


def test_start_job_creates_ledger(tmp_path):
    repo, output = _paths(tmp_path)
    job = js.start_job(repo, output, base_commit="abc123")

    assert job is not None
    assert job["phase"] == "analyzing"
    assert job["attempt"] == 1
    assert job["resume"] == "rebuild"
    assert job["base_commit"] == "abc123"
    assert job["job_id"]

    on_disk = js.job_path(repo, output)
    assert on_disk.is_file()
    assert json.loads(on_disk.read_text(encoding="utf-8"))["job_id"] == job["job_id"]


def test_resume_partial_bumps_attempt_and_keeps_identity(tmp_path):
    repo, output = _paths(tmp_path)
    first = js.start_job(repo, output, base_commit="abc123")
    js.record_planned(repo, output, ["a", "b", "c"])
    js.mark_page_written(repo, output, "a.md")

    second = js.start_job(repo, output, base_commit="abc123")

    assert second is not None
    assert second["job_id"] == first["job_id"]
    assert second["attempt"] == 2
    assert second["resume"] == "partial"
    assert second["phase"] == "analyzing"
    assert js.missing_pages(second) == ["b", "c"]


def test_resumed_complete_job_is_persisted(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output, base_commit="abc123")
    js.record_planned(repo, output, ["a"])
    js.mark_page_written(repo, output, "a.md")

    second = js.start_job(repo, output, base_commit="abc123")

    assert second is not None
    assert second["resume"] == "persisted"
    assert js.missing_pages(second) == []


def test_moved_baseline_forces_rebuild(tmp_path):
    repo, output = _paths(tmp_path)
    first = js.start_job(repo, output, base_commit="abc123")
    js.record_planned(repo, output, ["a"])

    second = js.start_job(repo, output, base_commit="def456")

    assert second is not None
    assert second["job_id"] != first["job_id"]
    assert second["resume"] == "rebuild"
    assert second["attempt"] == 1
    assert second["base_commit"] == "def456"


def test_planned_and_written_counters(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    job = js.record_planned(repo, output, ["b", "a", "a"])

    assert job is not None
    assert job["phase"] == "planned"
    assert job["pages"]["planned"] == 2
    assert job["pages"]["planned_keys"] == ["a", "b"]
    assert job["pages"]["missing"] == ["a", "b"]

    job = js.mark_page_written(repo, output, "a.md")
    assert job is not None
    assert job["phase"] == "generating"
    assert job["pages"]["written"] == 1
    assert job["pages"]["missing"] == ["b"]

    # Re-writing the same page is idempotent for module pages.
    job = js.mark_page_written(repo, output, "a.md")
    assert job is not None
    assert job["pages"]["written"] == 1

    job = js.mark_page_written(repo, output, "overview.md", page_type="overview")
    assert job is not None
    assert job["pages"]["other_written"] == 1
    assert job["pages"]["written"] == 1


def test_planned_key_counts_regardless_of_page_type(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["overview", "a"])
    js.mark_page_written(repo, output, "a.md")

    job = js.mark_page_written(repo, output, "overview.md", page_type="overview")

    assert job is not None
    assert job["pages"]["written"] == 2
    assert js.missing_pages(job) == []


def test_finish_done_when_nothing_missing(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["a"])
    js.mark_page_written(repo, output, "a.md")

    job = js.finish_job(repo, output)

    assert job is not None
    assert job["phase"] == "done"
    assert job["finished_at"]
    summary = js.job_summary(job)
    assert summary is not None
    assert summary["pages"]["missing"] == 0


def test_degraded_is_resumable_and_closes_as_done(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["a", "b"])
    js.mark_page_written(repo, output, "a.md")

    job = js.finish_job(repo, output)
    assert job is not None
    assert job["phase"] == "degraded"
    assert js.missing_pages(job) == ["b"]

    # A resumed attempt refills the lost page and closes as ``done``.
    resumed = js.start_job(repo, output)
    assert resumed is not None
    assert resumed["resume"] == "partial"
    js.mark_page_written(repo, output, "b.md")
    job = js.finish_job(repo, output)

    assert job is not None
    assert job["phase"] == "done"


def test_degraded_history_does_not_block_done_after_resume(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_degraded(repo, output, stage="module", code="module_failed")

    resumed = js.start_job(repo, output)
    closed = js.finish_job(repo, output)

    assert resumed is not None
    assert resumed["resume"] == "persisted"
    assert closed is not None
    assert closed["phase"] == "done"
    assert [entry["code"] for entry in closed["degraded"]] == ["module_failed"]


def test_done_rejects_later_page_writes(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["a"])
    js.mark_page_written(repo, output, "a.md")
    js.finish_job(repo, output)

    job = js.mark_page_written(repo, output, "late.md")

    assert job is not None
    assert job["phase"] == "done"
    assert job["pages"]["written"] == 1


def test_failed_is_final(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.set_phase(repo, output, "failed")

    assert js.finish_job(repo, output) is None or js.load_job(repo, output)["phase"] == "failed"
    job = js.set_phase(repo, output, "generating")
    assert job is not None
    assert job["phase"] == "failed"


def test_degraded_record_and_summary(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    job = js.record_degraded(repo, output, stage="relation", code="relation_skipped", detail="x")

    assert job is not None
    assert job["degraded"][0]["code"] == "relation_skipped"
    assert js.job_summary(job)["degraded_count"] == 1


def test_unknown_phase_is_ignored(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)

    job = js.set_phase(repo, output, "sorting")

    assert job is not None
    assert job["phase"] == "analyzing"


def test_corrupt_ledger_is_fail_open(tmp_path):
    repo, output = _paths(tmp_path)
    path = js.job_path(repo, output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert js.load_job(repo, output) is None
    assert js.missing_pages(js.load_job(repo, output)) == []

    job = js.start_job(repo, output, base_commit="abc")
    assert job is not None
    assert job["resume"] == "rebuild"
    assert json.loads(path.read_text(encoding="utf-8"))["job_id"] == job["job_id"]


def test_updates_without_a_job_are_noops(tmp_path):
    repo, output = _paths(tmp_path)

    assert js.set_phase(repo, output, "planned") is None
    assert js.record_planned(repo, output, ["a"]) is None
    assert js.mark_page_written(repo, output, "a.md") is None
    assert js.finish_job(repo, output) is None
    assert not js.job_path(repo, output).exists()


def test_write_leaves_no_tmp_files(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["a"])

    leftovers = list(js.job_path(repo, output).parent.glob("job.json.*"))
    assert leftovers == []


def test_job_summary_exposes_missing_pages_but_not_full_key_lists(tmp_path):
    repo, output = _paths(tmp_path)
    js.start_job(repo, output)
    js.record_planned(repo, output, ["a", "b"])
    js.mark_page_written(repo, output, "a.md")

    summary = js.job_summary(js.load_job(repo, output))
    assert summary is not None
    assert set(summary["pages"]) == {"planned", "written", "other_written", "missing"}
    # Missing pages are the actionable resume input; planned/written stay on disk.
    assert summary["missing_pages"] == ["b"]
    assert "planned_keys" not in summary
    assert "written_keys" not in summary
    assert js.job_summary(None) is None


def test_ledger_is_wired_through_analyze_plan_write_close(analyzed_repo):
    """End-to-end: analyze_repo → save_module_tree → write_doc_file → close."""
    import asyncio

    from codewiki.mcp.tools.close_session import handle_close_session
    from codewiki.mcp.tools.doc_writer import handle_write_doc_file
    from codewiki.mcp.tools.module_tree import handle_save_module_tree

    repo, store = analyzed_repo
    output = repo / "repowiki"

    job = js.load_job(repo, output)
    assert job is not None
    assert job["phase"] == "analyzed"
    assert job["artifacts"]["module_tree"].endswith("module_tree.json")

    saved = json.loads(
        handle_save_module_tree(
            {
                "repo_path": str(repo),
                "module_tree": {"core": {"components": ["a.py::func_a"]}},
            },
            store,
        )
    )
    assert saved["status"] == "saved", saved

    job = js.load_job(repo, output)
    assert job is not None
    assert job["phase"] == "planned"
    assert js.missing_pages(job) == ["core", "overview"]
    # The response view handed to the host agent carries the same keys, so a
    # partial resume has something to work from.
    assert js.job_summary(job)["missing_pages"] == ["core", "overview"]

    for filename, page_type in (("core.md", "module"), ("overview.md", "overview")):
        written = json.loads(
            asyncio.run(
                handle_write_doc_file(
                    {
                        "repo_path": str(repo),
                        "filename": filename,
                        "page_type": page_type,
                        "content": f"# {filename[:-3]}\n\nbody\n",
                    },
                    store,
                )
            )
        )
        assert written.get("status") == "created", written

    job = js.load_job(repo, output)
    assert job is not None
    assert js.missing_pages(job) == []

    closed = json.loads(handle_close_session({"repo_path": str(repo)}, store))
    assert closed["status"] == "closed", closed
    assert closed["job"]["phase"] == "done"
    assert closed["job"]["pages"] == {"planned": 2, "written": 2, "other_written": 0, "missing": 0}
    assert closed["job"]["missing_pages"] == []

    metadata = json.loads((output / ".meta" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["job_id"] == closed["job"]["job_id"]


def test_close_reports_missing_pages_as_degraded(analyzed_repo):
    """Closing with planned-but-unwritten pages must not claim success."""
    from codewiki.mcp.tools.close_session import handle_close_session
    from codewiki.mcp.tools.module_tree import handle_save_module_tree

    repo, store = analyzed_repo
    output = repo / "repowiki"

    handle_save_module_tree(
        {"repo_path": str(repo), "module_tree": {"core": {"components": ["a.py::func_a"]}}},
        store,
    )

    closed = json.loads(handle_close_session({"repo_path": str(repo)}, store))
    assert closed["status"] == "closed", closed
    assert closed["job"]["phase"] == "degraded"
    assert closed["job"]["pages"]["missing"] == 2


def test_no_changes_run_closes_the_ledger(analyzed_repo, monkeypatch):
    """The no_changes early return must not leave a job stuck in analyzing."""
    from codewiki.mcp.cache import AnalysisCache
    from codewiki.mcp.tools.analysis import handle_analyze_repo

    repo, store = analyzed_repo
    output = repo / "repowiki"

    # The tmp repo's repowiki/ is untracked, so a real detect_changes would
    # report doc churn; pin the no_changes branch directly.
    monkeypatch.setattr(AnalysisCache, "is_fresh", lambda self: True)
    monkeypatch.setattr(
        AnalysisCache,
        "detect_changes",
        lambda self: {"no_changes": True, "changed_files": [], "method": "git"},
    )

    resp = json.loads(handle_analyze_repo({"repo_path": str(repo)}, store))

    assert resp["changes"]["no_changes"] is True, resp.get("changes")
    assert resp["job"]["phase"] == "done"
    assert js.load_job(repo, output)["phase"] == "done"
