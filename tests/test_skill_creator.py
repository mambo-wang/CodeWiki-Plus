"""Tests for skill-creator T2: prepare + submit compile loop (issue #25).

Covers the first two modes of skill_creator (docs/skill-creator需求与设计
方案.md §4.1-§4.3, ADR-0004):

- prepare: candidate selection (unabsorbed scenarios / stable
  pitfall-lesson-decision notes), per-skill open-issue aggregation, capacity
  grading, conflict pre-check, zero side effects
- submit: created draft lands with OKF frontmatter + bidirectional
  provenance + index rebuild; updated appends revisions; every validation
  failure returns its specific rule name; no_action (empty report) is legal;
  anti-fragmentation (batch > 1 created) and capacity (orange) rejection
"""

import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import skill_creator as sc
from codewiki.mcp.tools import wiki_search


# --------------------------------------------------------------------------- #
# Helpers (fixture style follows test_consolidation_p2 / test_skill_pages)
# --------------------------------------------------------------------------- #
_SECTIONS = ["工作场景", "适用条件", "核心 SOP", "判断逻辑", "禁忌与反模式"]

_SKILL_SCHEMA = {
    "page_types": {
        "skill": {
            "directory": "skills",
            "description": "SKILL.md draft zone",
            "required_sections": _SECTIONS,
        }
    }
}


def _mk_repo(tmp_path: Path) -> tuple[str, Path]:
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / "wiki" / "scenarios").mkdir(parents=True)
    (od / "wiki").mkdir(exist_ok=True)  # build_full_index legacy fallback scans wiki/
    (od / "schema.yaml").write_text(
        yaml.safe_dump(_SKILL_SCHEMA, allow_unicode=True), encoding="utf-8"
    )
    return str(repo), od


def _write_scenario(od: Path, name: str, body: str = "## Work context\nx") -> str:
    sdir = od / "wiki" / "scenarios"
    sdir.mkdir(parents=True, exist_ok=True)
    p = sdir / f"{name}.md"
    p.write_text(
        "---\n"
        + yaml.safe_dump(
            {"type": "Scenario", "title": name, "status": "draft", "metadata": {}},
            allow_unicode=True,
        )
        + "---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return f"wiki/scenarios/{name}.md"


def _write_note(
    od: Path,
    name: str,
    note_type: str = "pitfall",
    status: str = "stable",
) -> str:
    p = od / "notes" / f"{name}.md"
    p.write_text(
        "---\n"
        + yaml.safe_dump(
            {"type": note_type, "title": name, "status": status, "metadata": {}},
            allow_unicode=True,
        )
        + "---\n\n## 背景\n\nbody of the note\n",
        encoding="utf-8",
    )
    return f"notes/{name}.md"


def _write_skill_draft(od: Path, name: str, source_refs: list[str] | None = None) -> str:
    sk_dir = od / "skills" / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"summary": f"summary of {name}"}
    if source_refs:
        meta["source_refs"] = source_refs
    p = sk_dir / "SKILL.md"
    p.write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "name": name,
                "description": f"当遇到 {name} 场景时执行对应 SOP",
                "type": "Skill",
                "status": "draft",
                "metadata": meta,
            },
            allow_unicode=True,
        )
        + "---\n\n"
        + "\n".join(f"## {s}\n\ncontent" for s in _SECTIONS)
        + "\n",
        encoding="utf-8",
    )
    return f"skills/{name}/SKILL.md"


def _write_issues(od: Path, issues: dict) -> None:
    meta = od / ".meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "issues.json").write_text(
        json.dumps({"version": 1, "issues": issues}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _issue(iid: str, page: str, status: str = "open") -> dict:
    return {
        "id": iid,
        "issue_type": "custom",
        "page_path": page,
        "description": f"issue on {page}",
        "severity": "warning",
        "created_at": "2026-09-01T00:00:00",
        "updated_at": "2026-09-02T00:00:00",
        "status": status,
        "occurrences": 1,
        "updates": [],
    }


def _call(repo: str, args: dict) -> dict:
    store = SessionStore()
    return json.loads(sc.handle_skill_creator({"repo_path": repo, **args}, store))


def _fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    end = text.find("---", 3)
    return yaml.safe_load(text[3:end])


def _snapshot(od: Path) -> dict:
    return {
        str(p.relative_to(od)).replace("\\", "/"): p.read_bytes()
        for p in sorted(od.rglob("*"))
        if p.is_file()
    }


def _skill_entry(name: str, **overrides) -> dict:
    entry = {
        "name": name,
        "action": "created",
        "description": f"When {name} errors appear, run the recovery SOP before retrying",
        "body": "\n".join(f"## {s}\n\ncontent for {s}" for s in _SECTIONS),
        # valid default so rule-specific cases don't trip source_refs_required
        # first; the source_refs cases override it explicitly
        "source_refs": ["notes/some-note.md"],
        "summary": f"{name} skill summary",
    }
    entry.update(overrides)
    return entry


# --------------------------------------------------------------------------- #
# 1. prepare
# --------------------------------------------------------------------------- #
def test_prepare_lists_unabsorbed_candidates_zero_side_effects(tmp_path):
    repo, od = _mk_repo(tmp_path)
    absorbed_scen = _write_scenario(od, "absorbed-scene")
    free_scen = _write_scenario(od, "free-scene")
    absorbed_note = _write_note(od, "absorbed-note")
    _write_note(od, "free-note", note_type="lesson")
    _write_note(od, "draft-note", status="draft")  # not stable
    _write_note(od, "wrong-type-note", note_type="general")  # wrong type
    # existing skill absorbs absorbed-scene + absorbed-note
    _write_skill_draft(od, "existing-skill", source_refs=[absorbed_scen, absorbed_note])

    before = _snapshot(od)
    resp = _call(repo, {"mode": "prepare"})
    assert resp["status"] == "prepared"

    # candidates: only unabsorbed scenario + unabsorbed stable note
    assert [c["file"] for c in resp["candidates"]["scenarios"]] == [free_scen]
    assert [c["file"] for c in resp["candidates"]["notes"]] == ["notes/free-note.md"]
    assert resp["candidates"]["total"] == 2
    assert resp["candidates"]["scenarios"][0]["est_tokens"] > 0

    # draft-zone index carries name/status/summary
    assert [s["name"] for s in resp["skills_index"]] == ["existing-skill"]
    assert resp["skills_index"][0]["status"] == "draft"

    # guidance fields
    assert resp["system_prompt"] and "工作场景" in resp["system_prompt"]
    assert resp["fragmentation_discipline"]
    assert resp["capacity"]["warning"] == "none"
    assert resp["capacity"]["max"] == 12

    # zero side effects
    assert _snapshot(od) == before


def test_prepare_capacity_grading_and_conflict_precheck(tmp_path):
    repo, od = _mk_repo(tmp_path)
    for i in range(9):
        _write_skill_draft(od, f"skill-{i}")
    resp = _call(repo, {"mode": "prepare"})
    assert resp["capacity"]["current"] == 9
    assert resp["capacity"]["warning"] == "orange"

    for i in range(9, 12):
        _write_skill_draft(od, f"skill-{i}")
    resp = _call(repo, {"mode": "prepare"})
    assert resp["capacity"]["current"] == 12
    assert resp["capacity"]["warning"] == "red"

    # conflict pre-check: topic nearly identical to an existing name
    # (pure-word overlap — CJK chars are tokenized per-char, which dilutes
    # Jaccard below the 0.6 threshold by design)
    resp = _call(repo, {"mode": "prepare", "topic": "skill 3 handler"})
    assert resp["conflict_precheck"]["provided"] is True
    warned = {w["skill"] for w in resp["conflict_precheck"]["warnings"]}
    assert "skill-3" in warned
    # without a topic: no warnings, just the hint
    resp = _call(repo, {"mode": "prepare"})
    assert resp["conflict_precheck"]["provided"] is False
    assert resp["conflict_precheck"]["warnings"] == []


def test_prepare_aggregates_open_issues_per_skill(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill_draft(od, "target-skill")
    _write_note(od, "some-note")
    _write_issues(
        od,
        {
            "id1": _issue("id1", "skills/target-skill/SKILL.md"),
            "id2": _issue("id2", "skills/target-skill/SKILL.md"),
            "id3": _issue("id3", "skills/target-skill/SKILL.md", status="resolved"),
            "id4": _issue("id4", "notes/some-note.md"),  # not a skill page
        },
    )
    resp = _call(repo, {"mode": "prepare"})
    assert resp["open_issues_by_skill"] == [
        {
            "skill": "target-skill",
            "issues": [
                {"id": "id1", "issue_type": "custom", "description": "issue on skills/target-skill/SKILL.md",
                 "severity": "warning", "updated_at": "2026-09-02T00:00:00"},
                {"id": "id2", "issue_type": "custom", "description": "issue on skills/target-skill/SKILL.md",
                 "severity": "warning", "updated_at": "2026-09-02T00:00:00"},
            ],
        }
    ]


# --------------------------------------------------------------------------- #
# 2. submit: created — draft file + provenance + index rebuild
# --------------------------------------------------------------------------- #
def test_submit_created_writes_skill_backlinks_and_rebuilds_index(tmp_path):
    repo, od = _mk_repo(tmp_path)
    scen = _write_scenario(od, "redis-scene")
    note = _write_note(od, "redis-note", note_type="decision")
    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    _skill_entry(
                        "redis-pool-ops",
                        source_refs=[scen, note],
                        revision_note="first compile from redis materials",
                    )
                ]
            },
        },
    )
    assert resp["status"] == "completed", resp
    skill_path = od / "skills" / "redis-pool-ops" / "SKILL.md"
    assert skill_path.is_file()

    fm = _fm(skill_path)
    assert fm["name"] == "redis-pool-ops"
    assert fm["type"] == "Skill"
    assert fm["status"] == "draft"
    assert fm["description"].startswith("When redis-pool-ops")
    assert fm["generated"]["by"].startswith("codewiki/")
    assert fm["stale_after"]
    assert set(fm["metadata"]["source_refs"]) == {scen, note}
    assert len(fm["metadata"]["revisions"]) == 1
    assert fm["metadata"]["revisions"][0]["reason"] == "first compile from redis materials"
    assert fm["metadata"]["revisions"][0]["source"] == "skill_creator"

    # bidirectional provenance: materials got compiled_into backlinks
    skill_rel = "skills/redis-pool-ops/SKILL.md"
    assert skill_rel in _fm(od / scen)["metadata"]["compiled_into"]
    assert skill_rel in _fm(od / note)["metadata"]["compiled_into"]

    # index rebuilt: the draft is indexed with source="skill"
    idx = wiki_search._load_index(od)
    assert "skills/redis-pool-ops/SKILL.md" in idx.docs
    assert idx.docs["skills/redis-pool-ops/SKILL.md"]["source"] == "skill"

    # the absorbed material is no longer a candidate
    again = _call(repo, {"mode": "prepare"})
    assert again["candidates"]["scenarios"] == []
    assert again["candidates"]["notes"] == []


def test_submit_updated_appends_revision_and_merges_refs(tmp_path):
    repo, od = _mk_repo(tmp_path)
    scen1 = _write_scenario(od, "scene-one")
    note1 = _write_note(od, "note-one")
    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {"skills": [_skill_entry("iter-skill", source_refs=[scen1, note1])]},
        },
    )
    assert resp["status"] == "completed"

    note2 = _write_note(od, "note-two", note_type="lesson")
    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    _skill_entry(
                        "iter-skill",
                        action="updated",
                        source_refs=["notes/note-two.md"],
                        revision_note="fold in lesson feedback",
                    )
                ]
            },
        },
    )
    assert resp["status"] == "completed", resp
    fm = _fm(od / "skills" / "iter-skill" / "SKILL.md")
    revisions = fm["metadata"]["revisions"]
    assert len(revisions) == 2
    assert revisions[-1]["reason"] == "fold in lesson feedback"
    # source_refs merged, deduplicated
    assert set(fm["metadata"]["source_refs"]) == {scen1, note1, "notes/note-two.md"}
    # new material got the backlink too
    assert "skills/iter-skill/SKILL.md" in _fm(od / note2)["metadata"]["compiled_into"]


# --------------------------------------------------------------------------- #
# 3. submit: validation failures name the exact rule
# --------------------------------------------------------------------------- #
def test_submit_validation_rule_names(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill_draft(od, "existing-skill")

    cases = [
        (_skill_entry("Bad Name!"), "name_slug"),
        (_skill_entry("ok-name", description="short"), "description_trigger"),
        (_skill_entry("ok-name", body="## 工作场景\n" + "x" * 9000), "body_too_large"),
        (
            _skill_entry(
                "ok-name",
                body="## 工作场景\nrun C:\\Users\\john\\script",
                source_refs=["notes/some-note.md"],
            ),
            "sensitive_content",
        ),
        (
            _skill_entry(
                "ok-name",
                body="## 工作场景\nkey sk-abc123def456ghi789jkl012 here",
                source_refs=["notes/some-note.md"],
            ),
            "sensitive_content",
        ),
        (_skill_entry("ok-name", source_refs=[]), "source_refs_required"),
        (_skill_entry("ok-name", action="installed"), "action_invalid"),
        (_skill_entry("existing-skill"), "name_conflict"),
        (_skill_entry("ghost-skill", action="updated"), "not_found"),
        (_skill_entry("ok-name", body="   "), "body_required"),
        (_skill_entry("ok-name", source_refs=["../../etc/passwd"]), "source_refs_invalid"),
    ]
    for entry, rule in cases:
        resp = _call(repo, {"mode": "submit", "report": {"skills": [entry]}})
        assert resp["status"] == "error", (rule, resp)
        rules = {e["rule"] for e in resp["errors"]}
        assert rule in rules, (rule, resp["errors"])

    # nothing was written by any failing round
    assert not (od / "skills" / "ok-name").exists()
    assert _snapshot(od / "skills") == _snapshot(od / "skills")


def test_submit_invalid_mode_and_report_shape(tmp_path):
    repo, od = _mk_repo(tmp_path)
    resp = _call(repo, {"mode": "install", "name": "x"})
    assert "error" in resp and "issue #26" in resp["error"]
    resp = _call(repo, {"mode": "bogus"})
    assert "error" in resp
    resp = _call(repo, {"mode": "submit"})  # missing report
    assert "error" in resp


# --------------------------------------------------------------------------- #
# 4. no_action + anti-fragmentation + capacity enforcement
# --------------------------------------------------------------------------- #
def test_submit_empty_report_is_legal_no_action(tmp_path):
    repo, od = _mk_repo(tmp_path)
    before = _snapshot(od)
    resp = _call(repo, {"mode": "submit", "report": {"skills": []}})
    assert resp["status"] == "no_action"
    assert not (od / "skills").exists()
    assert _snapshot(od) == before


def test_submit_rejects_multiple_created_in_one_batch(tmp_path):
    repo, od = _mk_repo(tmp_path)
    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    _skill_entry("skill-a", source_refs=["notes/n.md"]),
                    _skill_entry("skill-b", source_refs=["notes/n.md"]),
                ]
            },
        },
    )
    assert resp["status"] == "error"
    rules = {e["rule"] for e in resp["errors"]}
    assert "batch_fragmentation" in rules
    # nothing written
    assert not (od / "skills").exists()


def test_submit_capacity_orange_blocks_create_allows_update(tmp_path):
    repo, od = _mk_repo(tmp_path)
    for i in range(9):  # orange line: 9 live skills
        _write_skill_draft(od, f"cap-{i}")
    note = _write_note(od, "cap-note")

    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {"skills": [_skill_entry("brand-new", source_refs=[note])]},
        },
    )
    assert resp["status"] == "error"
    rules = {e["rule"] for e in resp["errors"]}
    assert "capacity_orange" in rules
    assert not (od / "skills" / "brand-new").exists()

    # UPDATE is still allowed at orange
    resp = _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    _skill_entry(
                        "cap-0",
                        action="updated",
                        source_refs=[note],
                        revision_note="orange update",
                    )
                ]
            },
        },
    )
    assert resp["status"] == "completed", resp
    fm = _fm(od / "skills" / "cap-0" / "SKILL.md")
    assert fm["description"].startswith("When cap-0")
    assert fm["metadata"]["revisions"][-1]["reason"] == "orange update"
