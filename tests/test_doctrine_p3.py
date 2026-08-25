"""Tests for P3: L3 Project Operating Doctrine (team-memory fusion 阶段二).

Covers docs/团队记忆融合-L2场景聚合与L3-Doctrine设计方案.md §4.4:

- refresh_doctrine prepare (current doctrine / changed scenes / stats / trigger)
- submit: char cap enforcement, OKF frontmatter + source_scenarios provenance,
  doctrine counter reset, rolling backup (keep 3)
- query_wiki(mode='overview') injects doctrine + scene navigation
- consolidate_notes submit cascade: doctrine_hint when doctrine counter is due
"""
import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import aggregation_state as agg
from codewiki.mcp.tools import doctrine as doc_tool
from codewiki.mcp.tools import note_consolidation as cons
from codewiki.mcp.tools.knowledge_loop import (
    handle_ingest_note, handle_confirm_note, handle_query_wiki,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _set_thresholds(repo: str, cons_t: int = 10, doctrine_t: int = 50,
                    max_scenes: int = 15, cap: int = 1200):
    od = Path(repo) / "repowiki"
    od.mkdir(parents=True, exist_ok=True)
    schema = {"conventions": {"aggregation": {
        "consolidation_threshold": cons_t,
        "doctrine_threshold": doctrine_t,
        "hint_interval": 5,
        "max_scenarios": max_scenes,
        "doctrine_max_chars": cap,
    }}}
    (od / "schema.yaml").write_text(yaml.safe_dump(schema), encoding="utf-8")


def _ingest_and_confirm(repo: str, title: str) -> str:
    store = SessionStore()
    r = json.loads(handle_ingest_note({
        "output_dir": f"{repo}/repowiki",
        "title": title, "note_type": "decision",
        "content": "## Background\nbody", "status": "draft",
    }, store))
    nf = Path(r["note_path"]).name
    handle_confirm_note({"output_dir": f"{repo}/repowiki", "note_file": nf}, store)
    return nf


def _write_scenario(repo: str, name: str) -> str:
    sdir = Path(repo) / "repowiki" / "wiki" / "scenarios"
    sdir.mkdir(parents=True, exist_ok=True)
    fm = {"type": "Scenario", "title": name, "status": "draft",
          "generated": {"by": "test/agent", "at": "2020-01-01T00:00:00Z"},
          "metadata": {"heat": 1, "summary": f"summary of {name}",
                       "source_notes": ["notes/seed.md"]}}
    p = sdir / f"{name}.md"
    p.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True) +
                 "---\n\n## Core SOP\ndo the thing\n", encoding="utf-8")
    return f"wiki/scenarios/{name}.md"


def _refresh(repo: str, args: dict) -> dict:
    store = SessionStore()
    payload = {"output_dir": f"{repo}/repowiki", **args}
    return json.loads(doc_tool.handle_refresh_doctrine(payload, store))


def _doctrine_text(repo: str) -> str:
    return (Path(repo) / "repowiki" / "wiki" / "doctrine.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. prepare
# --------------------------------------------------------------------------- #
def test_prepare_reports_state_and_changed_scenes(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, doctrine_t=2)
    _ingest_and_confirm(repo, "Doctrine prep note one")
    _ingest_and_confirm(repo, "Doctrine prep note two")
    _write_scenario(repo, "scene-a")

    resp = _refresh(repo, {"mode": "prepare"})
    assert resp["status"] == "prepared"
    assert resp["doctrine_exists"] is False
    assert resp["current_doctrine"] == ""
    assert resp["char_cap"] == 1200
    assert resp["stats"]["confirmed_notes"] == 2
    assert resp["stats"]["scenes"] == 1
    # no last_doctrine_at yet → every scene counts as changed (cold start)
    assert resp["stats"]["changed_scenes"] == 1
    assert "counter 2 >= threshold 2" in resp["trigger"]
    assert resp["system_prompt"] and "SIX DIMENSIONS" in resp["system_prompt"]


# --------------------------------------------------------------------------- #
# 2. submit: cap + write + counter reset + backup
# --------------------------------------------------------------------------- #
def test_submit_rejects_over_cap_content(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, cap=1200)
    long_content = "# Team Operating Doctrine\n" + "x" * 1300
    resp = _refresh(repo, {"mode": "submit", "content": long_content})
    assert resp["status"] == "rejected"
    assert resp["chars"] > resp["char_cap"]
    assert not (Path(repo) / "repowiki" / "wiki" / "doctrine.md").exists()


def test_submit_writes_doctrine_with_provenance_and_resets(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, doctrine_t=2)
    _ingest_and_confirm(repo, "Doctrine note alpha")
    _ingest_and_confirm(repo, "Doctrine note beta")
    scen = _write_scenario(repo, "scene-prov")

    body = "# Team Operating Doctrine\n> Operating Thesis: verify before merge\n"
    resp = _refresh(repo, {"mode": "submit", "content": body})
    assert resp["status"] == "completed", resp
    assert resp["counters"]["notes_since_last_doctrine"] == 0
    assert resp["source_scenarios"] == 1

    text = _doctrine_text(repo)
    assert "type: Doctrine" in text
    assert "status: draft" in text
    assert scen in text  # source_scenarios provenance
    assert "verify before merge" in text

    state = agg.load_state(Path(repo) / "repowiki")
    assert state["notes_since_last_doctrine"] == 0
    assert state["last_doctrine_at"]

    # second prepare: no counter pressure, scene no longer "changed"
    again = _refresh(repo, {"mode": "prepare"})
    assert again["doctrine_exists"] is True
    assert "manual refresh" in again["trigger"]
    assert again["stats"]["changed_scenes"] == 0


def test_submit_does_not_keep_backups(tmp_path):
    # Backup mechanism was removed (decision): doctrine is a small file, git
    # history is enough for rollback; .backup files polluted the full-text index.
    repo = str(tmp_path)
    _set_thresholds(repo)
    for i in range(2):
        resp = _refresh(repo, {"mode": "submit",
                               "content": f"# Doctrine v{i}\nthesis {i}"})
        assert resp["status"] == "completed"
    bdir = Path(repo) / "repowiki" / "wiki" / ".backup"
    assert not bdir.exists() or not list(bdir.glob("doctrine-*.md"))
    assert _doctrine_text(repo).count("thesis 1") == 1


# --------------------------------------------------------------------------- #
# 3. overview injection (§4.4 consumption entry)
# --------------------------------------------------------------------------- #
def test_query_wiki_overview_injects_doctrine_and_navigation(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo)
    _write_scenario(repo, "nav-scene")
    _refresh(repo, {"mode": "submit",
                    "content": "# Team Operating Doctrine\n> Operating Thesis: always lint before release"})

    store = SessionStore()
    resp = json.loads(handle_query_wiki({
        "output_dir": f"{repo}/repowiki",
        "mode": "overview",
        "query": "",
    }, store))
    assert "doctrine" in resp
    assert "always lint before release" in resp["doctrine"]
    assert "scene_navigation" in resp
    assert "nav-scene" in resp["scene_navigation"]


# --------------------------------------------------------------------------- #
# 4. consolidate → doctrine cascade hint (§4.5.2)
# --------------------------------------------------------------------------- #
def test_consolidate_submit_cascades_doctrine_hint(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, cons_t=10, doctrine_t=2)
    n1 = _ingest_and_confirm(repo, "Cascade note one")
    n2 = _ingest_and_confirm(repo, "Cascade note two")
    scen = _write_scenario(repo, "cascade-scene")

    store = SessionStore()
    resp = json.loads(cons.handle_consolidate_notes({
        "output_dir": f"{repo}/repowiki",
        "mode": "submit",
        "report": {"scenarios": [{
            "file": scen, "action": "updated",
            "source_notes": [f"notes/{n1}", f"notes/{n2}"],
        }]},
    }, store))
    assert resp["status"] == "completed"
    # doctrine counter (2) >= threshold (2) → cascade hint present
    assert "doctrine_hint" in resp
    assert resp["doctrine_hint"]["doctrine_due"] is True
    # consolidation counter reset, doctrine counter untouched
    assert resp["counters"]["notes_since_last_consolidation"] == 0
    assert resp["counters"]["notes_since_last_doctrine"] == 2


def test_consolidate_no_doctrine_hint_below_threshold(tmp_path):
    repo = str(tmp_path)
    _set_thresholds(repo, cons_t=10, doctrine_t=50)
    n1 = _ingest_and_confirm(repo, "Quiet cascade note")
    scen = _write_scenario(repo, "quiet-scene")

    store = SessionStore()
    resp = json.loads(cons.handle_consolidate_notes({
        "output_dir": f"{repo}/repowiki",
        "mode": "submit",
        "report": {"scenarios": [{
            "file": scen, "action": "updated",
            "source_notes": [f"notes/{n1}"],
        }]},
    }, store))
    assert resp["status"] == "completed"
    assert "doctrine_hint" not in resp
