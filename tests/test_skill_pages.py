"""Tests for skill-creator T1 vocabulary foundation (issue #24, ADR-0004).

Covers the draft-zone groundwork only — page-type routing (skills/ at the
repowiki root, NOT under wiki/), the skill_sections lint check (schema-driven
required sections), draft-zone indexing (source="skill"), and the effect-zone
isolation invariant (.codebuddy/skills/ is never scanned by repowiki tools).

The four-mode skill_creator tool itself is T2/T3 (issues #25/#26).
"""

import json
from pathlib import Path

import yaml

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import wiki_search
from codewiki.mcp.tools.page_router import (
    ensure_wiki_dirs,
    get_page_type_dir,
    resolve_wiki_paths,
)
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki


# --------------------------------------------------------------------------- #
# Helpers
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
    (od / "schema.yaml").write_text(yaml.safe_dump(_SKILL_SCHEMA, allow_unicode=True), encoding="utf-8")
    return str(repo), od


def _write_skill(
    od: Path, name: str, sections: list[str] | None = None
) -> Path:
    """Write a draft skill at skills/<name>/SKILL.md with the given sections."""
    body_sections = _SECTIONS if sections is None else sections
    body = "\n".join(f"## {s}\n\ncontent for {s}" for s in body_sections)
    sk_dir = od / "skills" / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    p = sk_dir / "SKILL.md"
    p.write_text(
        "---\n"
        + yaml.safe_dump(
            {"name": name, "description": f"当遇到 {name} 场景时使用", "type": "Skill", "status": "draft"},
            allow_unicode=True,
        )
        + "---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return p


def _lint(repo: str, checks: list[str] | None = None) -> list[dict]:
    store = SessionStore()
    args = {"repo_path": repo}
    if checks:
        args["checks"] = checks
    r = json.loads(handle_lint_wiki(args, store))
    return r.get("issues", [])


# --------------------------------------------------------------------------- #
# 1. Page-type routing: skill draft zone sits at the repowiki root
# --------------------------------------------------------------------------- #
def test_get_page_type_dir_skill_routes_to_repowiki_root(tmp_path):
    repo, od = _mk_repo(tmp_path)
    # schema override ("skills") resolves output_dir-relative, outside wiki/
    assert get_page_type_dir("skill", od) == od / "skills"


def test_get_page_type_dir_skill_without_schema_still_root(tmp_path):
    # No schema.yaml at all — code-level fallback (page_router skill branch)
    od = tmp_path / "bare" / "repowiki"
    od.mkdir(parents=True)
    assert get_page_type_dir("skill", od) == od / "skills"
    # and it must NOT fall into the wiki/ namespace like other page types
    assert get_page_type_dir("skill", od) != od / "wiki" / "skills"


def test_resolve_wiki_paths_and_ensure_dirs_include_skills(tmp_path):
    repo, od = _mk_repo(tmp_path)
    paths = resolve_wiki_paths(od)
    assert paths["skills"] == od / "skills"
    ensure_wiki_dirs(od)
    assert (od / "skills").is_dir()


# --------------------------------------------------------------------------- #
# 2. skill_sections lint check (schema-driven, draft zone only)
# --------------------------------------------------------------------------- #
def test_skill_sections_valid_draft_passes(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "demo-skill")  # full five-section skeleton
    issues = [i for i in _lint(repo, ["skill_sections"]) if i["check"] == "skill_sections"]
    assert issues == []


def test_skill_sections_missing_section_is_error(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "broken-skill", sections=_SECTIONS[:3] + _SECTIONS[4:])  # drop 判断逻辑
    issues = [i for i in _lint(repo, ["skill_sections"]) if i["check"] == "skill_sections"]
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert "判断逻辑" in issues[0]["message"]
    assert issues[0]["file"] == "skills/broken-skill/SKILL.md"


def test_skill_sections_included_in_all_checks(tmp_path):
    """'all' runs must include the new check — no silent opt-out."""
    from codewiki.mcp.tools.wiki_lint import _ALL_CHECKS

    assert "skill_sections" in _ALL_CHECKS


def test_skill_sections_ignores_frontmatter_only_body(tmp_path):
    """A body whose only 'headings' are frontmatter keys must fail the check."""
    repo, od = _mk_repo(tmp_path)
    sk_dir = od / "skills" / "fm-only"
    sk_dir.mkdir(parents=True)
    (sk_dir / "SKILL.md").write_text(
        "---\ntitle: x\n工作场景: not a heading\n---\nplain body without headings\n",
        encoding="utf-8",
    )
    issues = [i for i in _lint(repo, ["skill_sections"]) if i["check"] == "skill_sections"]
    assert len(issues) == len(_SECTIONS)


# --------------------------------------------------------------------------- #
# 3. Draft-zone indexing (source="skill", nested SKILL.md discovered)
# --------------------------------------------------------------------------- #
def test_build_full_index_counts_skills(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "indexed-skill")
    (od / "wiki").mkdir(exist_ok=True)
    r = wiki_search.build_full_index(od)  # no session / no DB -> legacy JSON
    assert r["skills_indexed"] == 1


def test_build_full_index_skill_doc_key_and_source(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "keyed-skill")
    wiki_search.build_full_index(od)
    # legacy JSON index: assert via search that the skill row exists with
    # source="skill" and a root-level skills/ key (not wiki/skills/)
    idx = wiki_search._load_index(od)
    keys = [k for k in idx.docs if k.startswith("skills/")]
    assert keys == ["skills/keyed-skill/SKILL.md"]
    assert idx.docs["skills/keyed-skill/SKILL.md"]["source"] == "skill"


def test_sqlite_index_counts_skills(tmp_path):
    """The AnalysisCache (SQLite) build path must index draft skills too."""
    from codewiki.mcp.cache import AnalysisCache

    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "sqlite-skill")
    _write_skill(od, "sqlite-skill-two")
    cache = AnalysisCache(Path(repo), db_path=Path(repo) / ".codewiki" / "analysis_cache.db")
    try:
        r = cache.build_search_index(od)
        assert r["skills_indexed"] == 2
        rows = cache.conn.execute(
            "SELECT doc_key, source FROM search_index WHERE source='skill'"
        ).fetchall()
        assert {row["doc_key"] for row in rows} == {
            "skills/sqlite-skill/SKILL.md",
            "skills/sqlite-skill-two/SKILL.md",
        }
    finally:
        cache.close()


# --------------------------------------------------------------------------- #
# 4. Effect-zone isolation: .codebuddy/skills/ is never scanned
# --------------------------------------------------------------------------- #
def test_effect_zone_files_never_indexed(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "draft-one")
    # effect zone lives at the REPO root, one level above the repowiki root
    eff = Path(repo) / ".codebuddy" / "skills" / "eff-one"
    eff.mkdir(parents=True)
    (eff / "SKILL.md").write_text(
        "---\nname: eff-one\ndescription: effect zone copy\n---\n\nbody\n", encoding="utf-8"
    )
    r = wiki_search.build_full_index(od)
    assert r["skills_indexed"] == 1  # only the draft-zone file
    idx = wiki_search._load_index(od)
    assert not [k for k in idx.docs if ".codebuddy" in k]


def test_effect_zone_files_never_linted(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_skill(od, "draft-one")
    # a heading-less SKILL.md in the effect zone would fail skill_sections
    # if it were scanned — it must never appear in lint output
    eff = Path(repo) / ".codebuddy" / "skills" / "eff-broken"
    eff.mkdir(parents=True)
    (eff / "SKILL.md").write_text("no frontmatter, no headings\n", encoding="utf-8")
    issues = [i for i in _lint(repo, ["skill_sections"]) if i["check"] == "skill_sections"]
    assert issues == []


# --------------------------------------------------------------------------- #
# 5. T5 recall isolation (issue #28): indexed, but never recalled
# --------------------------------------------------------------------------- #
def _mk_recognizable_skill(od: Path, name: str, marker: str) -> Path:
    """A skill whose body carries a unique BM25 marker token."""
    body = "\n".join(f"## {s}\n\n{marker} {s}" for s in _SECTIONS)
    sk_dir = od / "skills" / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    p = sk_dir / "SKILL.md"
    p.write_text(
        "---\n"
        + yaml.safe_dump(
            {"name": name, "description": f"当遇到 {name} 场景时使用 {marker}", "type": "Skill", "status": "draft"},
            allow_unicode=True,
        )
        + "---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return p


def test_search_legacy_never_recalls_skill(tmp_path):
    repo, od = _mk_repo(tmp_path)
    marker = "zxquniquemarker"
    _mk_recognizable_skill(od, "secret-skill", marker)
    # a note sharing the marker IS recalled — proving the index works and
    # the exclusion is specific to skills, not a broken search
    (od / "notes").mkdir(exist_ok=True)
    (od / "notes" / f"{marker}-note.md").write_text(
        f"---\ntitle: {marker} note\nstatus: stable\n---\n\n{marker} body\n",
        encoding="utf-8",
    )
    wiki_search.build_full_index(od)
    results = wiki_search.search(od, marker)
    files = [r["file"] for r in results]
    assert not [f for f in files if f.startswith("skills/")], files
    assert any(marker in f for f in files), "control note should be recalled"


def test_search_sqlite_never_recalls_skill(tmp_path):
    from codewiki.mcp.cache import AnalysisCache

    repo, od = _mk_repo(tmp_path)
    marker = "zxqsqliteuniquemarker"
    _mk_recognizable_skill(od, "sqlite-secret-skill", marker)
    (od / "notes").mkdir(exist_ok=True)
    (od / "notes" / f"{marker}-note.md").write_text(
        f"---\ntitle: {marker} note\nstatus: stable\n---\n\n{marker} body\n",
        encoding="utf-8",
    )
    cache = AnalysisCache(Path(repo), db_path=Path(repo) / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        # indexed but not recallable
        rows = cache.conn.execute(
            "SELECT COUNT(*) AS c FROM search_index WHERE source='skill'"
        ).fetchone()
        assert rows["c"] == 1
        results = cache.search(marker, output_dir=od)
        files = [r["file"] for r in results]
        assert not [f for f in files if f.startswith("skills/")], files
        assert any(marker in f for f in files), "control note should be recalled"
    finally:
        cache.close()


def test_search_expanded_terms_do_not_leak_skill(tmp_path):
    """The SQLite expanded-terms path must respect the same isolation."""
    from codewiki.mcp.cache import AnalysisCache

    repo, od = _mk_repo(tmp_path)
    marker = "zxqexpanduniquemarker"
    _mk_recognizable_skill(od, "expand-leak-skill", marker)
    cache = AnalysisCache(Path(repo), db_path=Path(repo) / ".codewiki" / "analysis_cache.db")
    try:
        cache.build_search_index(od)
        results = cache.search(
            "nearmiss",  # main query matches nothing…
            output_dir=od,
        )
        assert not [r for r in results if str(r["file"]).startswith("skills/")]
    finally:
        cache.close()


# --------------------------------------------------------------------------- #
# 6. T4 full SKILL.md check set (issue #27, design §4.5)
# --------------------------------------------------------------------------- #
def _write_raw_skill(
    od: Path,
    name: str,
    *,
    fm_overrides: dict | None = None,
    body: str | None = None,
) -> Path:
    """Hand-written draft (bypasses skill_creator submit) for backstop lint."""
    sk_dir = od / "skills" / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "name": name,
        "description": f"When {name} fires, run the recovery SOP",
        "type": "Skill",
        "status": "draft",
        "generated": {"by": "codewiki/test", "at": "2026-09-06T00:00:00Z"},
        "metadata": {
            "source_refs": ["notes/any-note.md"],
            "revisions": [{"at": "2026-09-06T00:00:00Z", "reason": "test", "source": "test"}],
        },
    }
    if fm_overrides:
        for k, v in fm_overrides.items():
            if k == "metadata":
                fm["metadata"].update(v)
            else:
                fm[k] = v
    text_body = body or "\n".join(f"## {s}\n\ncontent" for s in _SECTIONS)
    p = sk_dir / "SKILL.md"
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n" + text_body + "\n",
        encoding="utf-8",
    )
    return p


def _lint_skill(repo: str) -> list[dict]:
    return [i for i in _lint(repo, ["skill_lint"]) if i["check"] == "skill_lint"]


def test_skill_lint_clean_draft_passes(tmp_path):
    repo, od = _mk_repo(tmp_path)
    _write_raw_skill(od, "clean-skill")
    issues = [i for i in _lint_skill(repo) if i["severity"] == "error"]
    assert issues == []


def test_skill_lint_six_error_rules(tmp_path):
    repo, od = _mk_repo(tmp_path)
    # name_slug mismatch
    _write_raw_skill(od, "dir-a", fm_overrides={"name": "totally-different"})
    # description too short
    _write_raw_skill(od, "short-desc", fm_overrides={"description": "do it"})
    # frontmatter incomplete (no status, no source_refs)
    _write_raw_skill(
        od,
        "no-fm",
        fm_overrides={"status": "", "metadata": {"source_refs": []}},
    )
    # body too large
    _write_raw_skill(od, "big-body", body="## 工作场景\n" + "x" * 9000)
    # sensitive content
    _write_raw_skill(od, "leaky", body="## 工作场景\nrun C:\\Users\\john\\s.ps1")
    # revisions missing though generated
    _write_raw_skill(
        od, "no-rev", fm_overrides={"metadata": {"revisions": []}}
    )
    issues = _lint_skill(repo)
    errors = {(i["file"], i["message"].split(":")[0]) for i in issues if i["severity"] == "error"}
    rels = {f for f, _ in errors}
    assert "skills/dir-a/SKILL.md" in rels
    assert "skills/short-desc/SKILL.md" in rels
    assert "skills/no-fm/SKILL.md" in rels
    assert "skills/big-body/SKILL.md" in rels
    assert "skills/leaky/SKILL.md" in rels
    assert "skills/no-rev/SKILL.md" in rels


def test_skill_lint_possibly_stale(tmp_path):
    repo, od = _mk_repo(tmp_path)
    # material note exists and is stable -> no warning
    (od / "notes").mkdir(exist_ok=True)
    (od / "notes" / "mat.md").write_text(
        "---\ntype: pitfall\ntitle: mat\nstatus: stable\n---\nbody\n", encoding="utf-8"
    )
    _write_raw_skill(od, "fresh-skill", fm_overrides={"metadata": {"source_refs": ["notes/mat.md"]}})
    assert not [i for i in _lint_skill(repo) if "stale" in i["message"]]

    # material goes deprecated -> warning
    (od / "notes" / "mat.md").write_text(
        "---\ntype: pitfall\ntitle: mat\nstatus: deprecated\n---\nbody\n", encoding="utf-8"
    )
    stale = [i for i in _lint_skill(repo) if "possibly stale" in i["message"]]
    assert len(stale) == 1 and stale[0]["severity"] == "warning"

    # material removed entirely -> warning too
    (od / "notes" / "mat.md").unlink()
    stale = [i for i in _lint_skill(repo) if "possibly stale" in i["message"]]
    assert len(stale) == 1


def test_skill_lint_drift_after_revision(tmp_path):
    repo, od = _mk_repo(tmp_path)
    from codewiki.mcp.tools.skill_creator import _normalized_hash

    _write_raw_skill(od, "drifty-skill")
    # simulate install stamping: hash of current content
    p = od / "skills" / "drifty-skill" / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    h = _normalized_hash(
        "drifty-skill", "When drifty-skill fires, run the recovery SOP", "## x"
    )
    fm = yaml.safe_load(text[3 : text.find("---", 3)])
    fm["metadata"]["installed_hash"] = h
    p.write_text(
        "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n\n## revised body\n",
        encoding="utf-8",
    )
    drift = [i for i in _lint_skill(repo) if "drifted" in i["message"]]
    assert len(drift) == 1 and drift[0]["severity"] == "warning"
    assert "effect zone still serves the old version" in drift[0]["message"]


def test_skill_lint_capacity_grading(tmp_path):
    repo, od = _mk_repo(tmp_path)
    for i in range(_ORANGE := 9):
        _write_raw_skill(od, f"cap-{i}")
    warns = [i for i in _lint_skill(repo) if "near capacity" in i["message"]]
    assert len(warns) == 1 and warns[0]["severity"] == "warning"
    for i in range(9, 12):
        _write_raw_skill(od, f"cap-{i}")
    errs = [i for i in _lint_skill(repo) if "at/over capacity" in i["message"]]
    assert len(errs) == 1 and errs[0]["severity"] == "error"
