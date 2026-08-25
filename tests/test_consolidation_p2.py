"""Tests for P2: L2 scene-block consolidation (team-memory fusion 阶段二).

Covers docs/团队记忆融合-L2场景聚合与L3-Doctrine设计方案.md §4.3/§4.5:

- aggregation counters + threshold-crossing hints (§4.5.2, confirm_note 联动)
- wiki_stats / get_task_context counter exposure
- consolidate_notes prepare/submit (Mode C): pending selection, capacity
  grading, provenance (source_notes ⇄ consolidated_into), [DELETED] cleanup,
  validation errors, capacity enforcement, counter reset
- lint scenario_capacity / scenario_orphan checks
"""
import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import aggregation_state as agg
from codewiki.mcp.tools import note_consolidation as cons
from codewiki.mcp.tools.knowledge_loop import (
    handle_ingest_note, handle_confirm_note, handle_reject_note, handle_wiki_stats,
)
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _set_thresholds(repo: str, cons_t: int = 3, hint_interval: int = 2,
                    max_scenes: int = 15):
    od = Path(repo) / "repowiki"
    od.mkdir(parents=True, exist_ok=True)
    schema = {"conventions": {"aggregation": {
        "consolidation_threshold": cons_t,
        "doctrine_threshold": 50,
        "hint_interval": hint_interval,
        "max_scenarios": max_scenes,
    }}}
    (od / "schema.yaml").write_text(yaml.safe_dump(schema), encoding="utf-8")


def _ingest(repo: str, title: str, note_type: str = "decision",
            content: str = "## Background\nbody") -> str:
    store = SessionStore()
    r = json.loads(handle_ingest_note({
        "output_dir": f"{repo}/repowiki",
        "title": title,
        "note_type": note_type,
        "content": content,
        "status": "draft",
    }, store))
    assert r.get("status") in ("ingested", "already_exists"), r
    return Path(r["note_path"]).name


def _confirm(repo: str, note_file: str) -> dict:
    store = SessionStore()
    return json.loads(handle_confirm_note({
        "output_dir": f"{repo}/repowiki",
        "note_file": note_file,
    }, store))


def _write_scenario(repo: str, name: str, body: str = "## Work context\nx",
                    with_provenance: bool = True) -> str:
    sdir = Path(repo) / "repowiki" / "wiki" / "scenarios"
    sdir.mkdir(parents=True, exist_ok=True)
    meta = {"heat": 1}
    if with_provenance:
        meta["source_notes"] = ["notes/seed.md"]
    fm = {
        "type": "Scenario",
        "title": name,
        "status": "draft",
        "metadata": meta,
    }
    p = sdir / f"{name}.md"
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n" + body + "\n",
        encoding="utf-8",
    )
    return f"wiki/scenarios/{name}.md"


def _fm(repo: str, rel: str) -> dict:
    text = (Path(repo) / "repowiki" / rel).read_text(encoding="utf-8")
    end = text.find("---", 3)
    return yaml.safe_load(text[3:end])


def _consolidate(repo: str, args: dict) -> dict:
    store = SessionStore()
    payload = {"output_dir": f"{repo}/repowiki", **args}
    return json.loads(cons.handle_consolidate_notes(payload, store))


# --------------------------------------------------------------------------- #
# 1. counters & hints (§4.5.2)
# --------------------------------------------------------------------------- #
def test_confirm_increments_counter_and_hints_with_interval(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, cons_t=3, hint_interval=2)

    hints = []
    for i in range(5):
        nf = _ingest(repo, f"Threshold note {i} alpha{i}")
        resp = _confirm(repo, nf)
        hints.append(resp.get("aggregation_hint"))

    # confirms 1,2: below threshold → no hint
    assert hints[0] is None and hints[1] is None
    # confirm 3: crosses threshold → hint fires
    assert hints[2] is not None and hints[2]["consolidation_due"] is True
    assert hints[2]["counters"]["notes_since_last_consolidation"] == 3
    # confirm 4: only 1 new since last hint (< interval 2) → silent
    assert hints[3] is None
    # confirm 5: 2 new since last hint → fires again
    assert hints[4] is not None

    state = agg.load_state(Path(repo) / "repowiki")
    assert state["notes_since_last_consolidation"] == 5


def test_wiki_stats_exposes_aggregation_section(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    nf = _ingest(repo, "Stats visibility note")
    _confirm(repo, nf)
    store = SessionStore()
    resp = json.loads(handle_wiki_stats(
        {"output_dir": f"{repo}/repowiki"}, store))
    # no retrieval stats DB yet → early return path must still carry counters
    assert "aggregation" in resp
    assert resp["aggregation"]["notes_since_last_consolidation"] == 1
    assert resp["aggregation"]["consolidation_threshold"] == 3


def test_get_task_context_exposes_aggregation(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    from codewiki.mcp.tools.task_manager import handle_create_task, handle_get_task_context
    store = SessionStore()
    r = json.loads(handle_create_task(
        {"output_dir": f"{repo}/repowiki", "title": "P2 smoke task"}, store))
    task_id = r["task"]["id"]
    resp = json.loads(handle_get_task_context(
        {"output_dir": f"{repo}/repowiki", "task_id": task_id}, store))
    assert resp["ok"] is True
    assert "aggregation" in resp
    assert resp["aggregation"]["notes_since_last_consolidation"] == 0


# --------------------------------------------------------------------------- #
# 2. consolidate_notes prepare
# --------------------------------------------------------------------------- #
def test_prepare_lists_only_pending_confirmed_notes(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    stable = _ingest(repo, "Stable candidate note")
    _confirm(repo, stable)
    _ingest(repo, "Draft only note")                      # stays draft
    rejected = _ingest(repo, "Rejected candidate note")
    store = SessionStore()
    handle_reject_note({"output_dir": f"{repo}/repowiki",
                        "note_file": rejected, "reason": "noise"}, store)

    resp = _consolidate(repo, {"mode": "prepare"})
    assert resp["status"] == "prepared"
    titles = [n["title"] for n in resp["pending_notes"]]
    assert "Stable candidate note" in titles
    assert "Draft only note" not in titles
    assert "Rejected candidate note" not in titles
    assert "system_prompt" in resp and resp["system_prompt"]
    assert resp["capacity"]["warning"] == "none"


def test_prepare_capacity_grading(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, max_scenes=3)
    for i in range(3):
        _write_scenario(repo, f"scene-{i}")
    resp = _consolidate(repo, {"mode": "prepare"})
    assert resp["capacity"]["current"] == 3
    assert resp["capacity"]["warning"] == "red"


# --------------------------------------------------------------------------- #
# 3. consolidate_notes submit
# --------------------------------------------------------------------------- #
def test_submit_records_provenance_and_resets_counter(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    n1 = _ingest(repo, "Redis pool pitfall knowledge")
    n2 = _ingest(repo, "Redis pool tuning decision")
    _confirm(repo, n1)
    _confirm(repo, n2)
    state = agg.load_state(Path(repo) / "repowiki")
    assert state["notes_since_last_consolidation"] == 2

    scen = _write_scenario(repo, "redis-运维方法", body="## Core SOP\ncheck pool",
                           with_provenance=False)
    resp = _consolidate(repo, {"mode": "submit", "report": {"scenarios": [{
        "file": scen,
        "action": "created",
        "source_notes": [f"notes/{n1}", f"notes/{n2}"],
        "summary": "Redis 连接池运维方法汇总",
        "heat": 1,
    }]}})
    assert resp["status"] == "completed", resp
    assert resp["counters"]["notes_since_last_consolidation"] == 0

    # scenario side: source_notes + summary/heat stamped
    sfm = _fm(repo, scen)
    assert set(sfm["metadata"]["source_notes"]) == {f"notes/{n1}", f"notes/{n2}"}
    assert sfm["metadata"]["summary"].startswith("Redis")
    assert sfm["metadata"]["heat"] == 1
    # note side: consolidated_into backlink
    assert scen in _fm(repo, f"notes/{n1}")["metadata"]["consolidated_into"]
    assert scen in _fm(repo, f"notes/{n2}")["metadata"]["consolidated_into"]

    # absorbed notes no longer pending
    again = _consolidate(repo, {"mode": "prepare"})
    assert again["pending_notes"] == []


def test_submit_deleted_cleans_soft_deleted_files(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    scen = _write_scenario(repo, "obsolete-scene")
    # rewrite body to the soft-delete marker (as the agent would)
    p = Path(repo) / "repowiki" / scen
    fm_text = p.read_text(encoding="utf-8")
    end = fm_text.find("---", 3)
    p.write_text(fm_text[:end + 3] + "\n[DELETED]\n", encoding="utf-8")

    resp = _consolidate(repo, {"mode": "submit", "report": {"scenarios": [
        {"file": scen, "action": "deleted"},
    ]}})
    assert resp["status"] == "completed"
    assert scen.replace("/", "/") in [r.replace("\\", "/") for r in resp["removed_deleted"]]
    assert not p.exists()


def test_submit_deleted_requires_marker(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    scen = _write_scenario(repo, "alive-scene")
    resp = _consolidate(repo, {"mode": "submit", "report": {"scenarios": [
        {"file": scen, "action": "deleted"},
    ]}})
    assert resp["status"] == "error"
    assert (Path(repo) / "repowiki" / scen).exists()


def test_submit_validation_error_keeps_counter(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    nf = _ingest(repo, "Counter guard note")
    _confirm(repo, nf)
    resp = _consolidate(repo, {"mode": "submit", "report": {"scenarios": [
        {"file": "wiki/scenarios/ghost.md", "action": "created", "source_notes": []},
    ]}})
    assert resp["status"] == "error"
    state = agg.load_state(Path(repo) / "repowiki")
    assert state["notes_since_last_consolidation"] == 1  # NOT reset


def test_submit_capacity_exceeded_blocks_reset(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, max_scenes=2)
    nf = _ingest(repo, "Capacity guard note")
    _confirm(repo, nf)
    files = [_write_scenario(repo, f"cap-{i}") for i in range(3)]
    resp = _consolidate(repo, {"mode": "submit", "report": {"scenarios": [
        {"file": f, "action": "updated", "source_notes": []} for f in files
    ]}})
    assert resp["status"] == "capacity_exceeded"
    assert resp["capacity"]["current"] == 3
    state = agg.load_state(Path(repo) / "repowiki")
    assert state["notes_since_last_consolidation"] == 1  # NOT reset


# --------------------------------------------------------------------------- #
# 4. lint checks
# --------------------------------------------------------------------------- #
def test_lint_scenario_capacity_and_orphan(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, max_scenes=2)
    _write_scenario(repo, "over-1", with_provenance=False)
    _write_scenario(repo, "over-2", with_provenance=False)
    _write_scenario(repo, "over-3", with_provenance=False)

    store = SessionStore()
    resp = json.loads(handle_lint_wiki(
        {"output_dir": f"{repo}/repowiki",
         "checks": ["scenario_capacity", "scenario_orphan"]}, store))
    checks = {i["check"] for i in resp["issues"]}
    assert "scenario_capacity" in checks
    cap = [i for i in resp["issues"] if i["check"] == "scenario_capacity"][0]
    assert cap["severity"] == "error"
    # orphan: no source_notes + never retrieved → info for all three
    orphans = [i for i in resp["issues"] if i["check"] == "scenario_orphan"]
    assert len(orphans) == 3
    assert all(i["severity"] == "info" for i in orphans)


def test_lint_wiki_schema_checks_enum_in_sync():
    """Regression (found in e2e acceptance): the lint_wiki inputSchema
    ``checks`` enum must stay in sync with wiki_lint._ALL_CHECKS — a missing
    entry makes MCP input validation reject the check before the handler runs.
    """
    from codewiki.mcp.registry import REGISTRY
    from codewiki.mcp.tools.wiki_lint import _ALL_CHECKS

    schema = REGISTRY["lint_wiki"].schema.inputSchema
    enum = set(schema["properties"]["checks"]["items"]["enum"])
    missing = _ALL_CHECKS - enum
    assert not missing, f"lint_wiki schema enum missing checks: {sorted(missing)}"
