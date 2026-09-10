"""Tests for draft-skill matching / material scoring (skill-creator §10).

Covers the three consumers of ``codewiki.src.skill_match`` and the status
lifecycle that makes "uninstalled draft" a meaningful state:

- tokenization + containment scoring (Jaccard was measured and rejected)
- draft filtering: only ``status: draft`` is matchable
- matching never leaks the skill body (ADR-0004 decision 2)
- material scoring: command density is the discriminator
- UserPromptSubmit hook branch: injects a pointer, writes nothing
- install → ``stable``; submit revision → back to ``draft``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from codewiki.mcp import _ide_hook as hook
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import skill_creator as sc
from codewiki.src import skill_match as sm

_SECTIONS = ["工作场景", "适用条件", "核心 SOP", "判断逻辑", "禁忌与反模式"]

_DESCRIPTION = (
    "当合入 fork 来源的 PR 且状态冲突时，先 git merge-tree 探测冲突，"
    "再在 worktree 隔离目录解冲突后 push fork 分支"
)


def _write_draft(
    skills_dir: Path, name: str, status: str = "draft", description: str = _DESCRIPTION
) -> Path:
    path = skills_dir / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "name": name,
                "description": description,
                "type": "Skill",
                "status": status,
                "metadata": {"summary": f"summary of {name}"},
            },
            allow_unicode=True,
        )
        + "---\n\n"
        + "\n".join(f"## {s}\n\nSECRET-BODY-MARKER-{s}" for s in _SECTIONS)
        + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# tokenize / containment
# --------------------------------------------------------------------------- #
def test_tokenize_mixes_cjk_bigrams_and_ascii():
    tokens = sm.tokenize("合入 fork 的 PR")
    assert "fork" in tokens
    assert "pr" in tokens
    assert "合入" in tokens
    # spaces and latin punctuation contribute nothing
    assert "" not in tokens


def test_containment_is_prompt_coverage_not_jaccard():
    """Regression guard for the measured Jaccard failure.

    A verbatim prefix of the description is a perfect match; Jaccard scored it
    0.205 (union inflated by the long description) which would never clear a
    0.6 gate. Containment must score it 1.0.
    """
    prompt = _DESCRIPTION[:24]
    a, b = sm.tokenize(prompt), sm.tokenize(_DESCRIPTION)
    assert sm.containment(a, b) == 1.0
    # Same pair under Jaccard sits well below the 0.6 gate that was originally
    # specified — on the real maintain-fork-pr-merge description it was 0.205.
    # A Jaccard gate would therefore never fire, on any length of description.
    assert len(a & b) / len(a | b) < 0.6


def test_containment_empty_sets_are_zero():
    assert sm.containment(set(), {"a"}) == 0.0
    assert sm.containment({"a"}, set()) == 0.0


# --------------------------------------------------------------------------- #
# draft filtering + matching
# --------------------------------------------------------------------------- #
def test_iter_draft_skills_only_returns_drafts(tmp_path: Path):
    d = tmp_path / "skills"
    _write_draft(d, "fresh", "draft")
    _write_draft(d, "installed", "stable")
    _write_draft(d, "gone", "deprecated")

    names = [s["name"] for s in sm.iter_draft_skills(str(d))]
    assert names == ["fresh"]


def test_iter_draft_skills_missing_dir_is_empty(tmp_path: Path):
    assert sm.iter_draft_skills(str(tmp_path / "nope")) == []


def test_match_hits_on_overlapping_prompt(tmp_path: Path):
    d = tmp_path / "skills"
    _write_draft(d, "fork-pr-conflict")
    hit = sm.match_draft_skills("当合入 fork 来源的 PR 且状态冲突时", str(d))
    assert hit is not None
    assert hit["name"] == "fork-pr-conflict"
    assert hit["score"] >= 0.5


def test_match_misses_on_unrelated_prompt(tmp_path: Path):
    d = tmp_path / "skills"
    _write_draft(d, "fork-pr-conflict")
    assert sm.match_draft_skills("把本周的会议纪要整理成一篇公众号文章", str(d)) is None


def test_match_ignores_very_short_prompts(tmp_path: Path):
    """A two-token prompt must not match on shared bigrams alone."""
    d = tmp_path / "skills"
    _write_draft(d, "fork-pr-conflict")
    assert sm.match_draft_skills("继续", str(d)) is None


def test_match_never_returns_the_body(tmp_path: Path):
    """ADR-0004 decision 2: name + description only, never the SKILL body."""
    d = tmp_path / "skills"
    _write_draft(d, "fork-pr-conflict")
    hit = sm.match_draft_skills("当合入 fork 来源的 PR 且状态冲突时", str(d))
    assert hit is not None
    assert set(hit) == {"name", "description", "file", "score"}
    assert "SECRET-BODY-MARKER" not in json.dumps(hit, ensure_ascii=False)


def test_match_returns_best_of_several(tmp_path: Path):
    d = tmp_path / "skills"
    _write_draft(d, "weak", description="一些完全不相关的技能描述内容放在这里")
    _write_draft(d, "strong", description=_DESCRIPTION)
    hit = sm.match_draft_skills("当合入 fork 来源的 PR 且状态冲突时", str(d))
    assert hit["name"] == "strong"


# --------------------------------------------------------------------------- #
# material scoring
# --------------------------------------------------------------------------- #
_CMD_HEAVY = (
    "---\nmetadata:\n  source_refs: [notes/a.md, notes/b.md]\n---\n\n"
    "## 核心 SOP\n\n1. git merge-tree 探测\n2. git worktree add 隔离\n"
    "3. git push 到 fork\n4. gh pr merge 收尾\n"
)


def test_score_material_worth_compiling():
    score = sm.score_skill_material(_CMD_HEAVY)
    assert score["cmd_hits"] >= 3
    assert score["notes_refs"] >= 2
    assert score["already_compiled"] is False
    assert score["worth_compiling"] is True


def test_score_material_rejects_prose_only_scenario():
    score = sm.score_skill_material(
        "---\nmetadata:\n  source_refs: [notes/a.md]\n---\n\n"
        "## 核心 SOP\n\n1. 先理解整体架构\n2. 再梳理模块边界\n"
    )
    assert score["cmd_hits"] == 0
    assert score["worth_compiling"] is False


def test_score_material_rejects_already_compiled():
    score = sm.score_skill_material(
        _CMD_HEAVY.replace("---\nmetadata:", "---\nmetadata:\n  compiled_into: [skills/x]")
    )
    assert score["already_compiled"] is True
    assert score["worth_compiling"] is False


def test_score_material_rejects_single_note_backing():
    score = sm.score_skill_material(
        "---\nmetadata:\n  source_refs: [notes/a.md]\n---\n\n"
        "1. git merge-tree\n2. git worktree add\n3. git push\n"
    )
    assert score["notes_refs"] == 1
    assert score["worth_compiling"] is False


# --------------------------------------------------------------------------- #
# hint payloads
# --------------------------------------------------------------------------- #
def test_build_skill_hint_match_shape():
    hint = sm.build_skill_hint("match", {"name": "x", "description": "d", "score": 0.7})
    assert hint["skill_hint"]["kind"] == "match"
    assert 'mode="install"' in hint["skill_hint"]["message"]


def test_build_skill_hint_material_shape():
    hint = sm.build_skill_hint(
        "material", {"file": "wiki/scenarios/a.md", "score": sm.score_skill_material(_CMD_HEAVY)}
    )
    assert hint["skill_hint"]["kind"] == "material"
    assert 'mode="prepare"' in hint["skill_hint"]["message"]


# --------------------------------------------------------------------------- #
# note scoring (2026-09-10): notes are the PRIMARY skill material — a scenario
# is aggregated and size-capped, a note keeps the sequence at full granularity.
# --------------------------------------------------------------------------- #
def test_score_note_procedure_is_worth_compiling():
    score = sm.score_skill_material(
        "## 完整流程\n\n1. uv build\n2. uv publish\n3. gh release create\n",
        kind="note",
        note_type="procedure",
    )
    assert score["kind"] == "note"
    assert score["worth_compiling"] is True


def test_score_note_ignores_note_refs_requirement():
    # A note cannot self-reference notes/, so that signal is scenario-only
    score = sm.score_skill_material(
        "1. uv build\n2. uv publish\n3. gh release create\n",
        kind="note",
        note_type="lesson",
    )
    assert score["notes_refs"] == 0
    assert score["worth_compiling"] is True


def test_score_note_prose_still_rejected():
    score = sm.score_skill_material(
        "先理解整体架构，再梳理模块边界", kind="note", note_type="lesson"
    )
    assert score["worth_compiling"] is False


def test_score_note_already_compiled_rejected():
    score = sm.score_skill_material(
        "metadata:\n  compiled_into: [skills/x]\n"
        "1. uv build\n2. uv publish\n3. gh release create\n",
        kind="note",
        note_type="procedure",
    )
    assert score["worth_compiling"] is False


def test_note_material_hint_points_at_notes_source():
    score = sm.score_skill_material(
        "1. uv build\n2. uv publish\n3. gh release create\n",
        kind="note",
        note_type="procedure",
    )
    hint = sm.build_skill_hint(
        "material", {"file": "notes/a.md", "kind": "note", "score": score}
    )
    msg = hint["skill_hint"]["message"]
    assert "笔记" in msg
    assert 'sources=["notes"]' in msg


def test_build_skill_hint_unknown_kind_is_empty():
    assert sm.build_skill_hint("nope", {}) == {}


# --------------------------------------------------------------------------- #
# UserPromptSubmit hook branch
# --------------------------------------------------------------------------- #
def _mk_repo(tmp_path: Path, skills: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "repowiki" / "skills").mkdir(parents=True)
    for name, status in (skills or {"fork-pr-conflict": "draft"}).items():
        _write_draft(repo / "repowiki" / "skills", name, status)
    return repo


def _run_hook(repo: Path, event: dict, tmp_path: Path, capsys) -> str:
    event_file = tmp_path / "event.json"
    event_file.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
    code = hook.main(
        ["--enable", "--conversation", str(event_file), "--repo-path", str(repo)]
    )
    assert code == 0
    return capsys.readouterr().out


def test_hook_user_prompt_injects_additional_context(tmp_path: Path, capsys):
    repo = _mk_repo(tmp_path)
    out = _run_hook(
        repo,
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "当合入 fork 来源的 PR 且状态冲突时",
            "repo_path": str(repo),
        },
        tmp_path,
        capsys,
    )
    payload = json.loads(out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "fork-pr-conflict" in ctx
    assert "SECRET-BODY-MARKER" not in ctx  # body never injected


def test_hook_user_prompt_silent_without_match(tmp_path: Path, capsys):
    repo = _mk_repo(tmp_path)
    out = _run_hook(
        repo,
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "把本周的会议纪要整理成一篇公众号文章",
        },
        tmp_path,
        capsys,
    )
    assert out == ""


def test_hook_user_prompt_writes_nothing(tmp_path: Path, capsys):
    repo = _mk_repo(tmp_path)
    wiki = repo / "repowiki"
    before = {str(p): p.read_bytes() for p in sorted(wiki.rglob("*")) if p.is_file()}
    _run_hook(
        repo,
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "当合入 fork 来源的 PR 且状态冲突时",
        },
        tmp_path,
        capsys,
    )
    after = {str(p): p.read_bytes() for p in sorted(wiki.rglob("*")) if p.is_file()}
    assert before == after


def test_hook_prompt_event_never_captures(tmp_path: Path, capsys):
    """A prompt event must not reach the capture path (no raw/ file created)."""
    repo = _mk_repo(tmp_path)
    _run_hook(
        repo,
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "当合入 fork 来源的 PR 且状态冲突时",
            "conversation": [{"role": "user", "content": "should not be captured"}],
        },
        tmp_path,
        capsys,
    )
    assert not (repo / "repowiki" / "raw").exists()


# --------------------------------------------------------------------------- #
# status lifecycle (install → stable, revision → draft)
# --------------------------------------------------------------------------- #
def _mk_skill_repo(tmp_path: Path, status: str = "draft") -> tuple[str, Path, Path]:
    repo = tmp_path / "repo"
    od = repo / "repowiki"
    (od / "notes").mkdir(parents=True)
    (od / "skills").mkdir(parents=True)
    (od / "wiki" / "scenarios").mkdir(parents=True)
    (od / "schema.yaml").write_text(
        yaml.safe_dump(
            {"page_types": {"skill": {"directory": "skills", "required_sections": _SECTIONS}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    draft = _write_draft(od / "skills", "fork-pr-conflict", status)
    return str(repo), od, draft


def _call(repo: str, args: dict) -> dict:
    return json.loads(sc.handle_skill_creator({"repo_path": repo, **args}, SessionStore()))


def _fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text[3 : text.find("---", 3)])


def test_install_flips_status_to_stable(tmp_path: Path):
    repo, od, draft = _mk_skill_repo(tmp_path)
    assert _fm(draft)["status"] == "draft"

    res = _call(repo, {"mode": "install", "name": "fork-pr-conflict"})
    assert res["status"] == "installed"

    fm = _fm(draft)
    assert fm["status"] == "stable"
    assert fm["metadata"]["installed_at"]


def test_installed_skill_is_no_longer_matchable(tmp_path: Path):
    repo, od, _ = _mk_skill_repo(tmp_path)
    assert sm.iter_draft_skills(str(od / "skills")) != []
    _call(repo, {"mode": "install", "name": "fork-pr-conflict"})
    assert sm.iter_draft_skills(str(od / "skills")) == []


def test_submit_revision_flips_status_back_to_draft(tmp_path: Path):
    repo, od, draft = _mk_skill_repo(tmp_path)
    _call(repo, {"mode": "install", "name": "fork-pr-conflict"})
    assert _fm(draft)["status"] == "stable"

    res = _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    {
                        "name": "fork-pr-conflict",
                        "action": "updated",
                        "description": "当合入 fork 来源的 PR 且状态冲突时执行修订后的 SOP",
                        "body": "\n".join(f"## {s}\n\nrevised" for s in _SECTIONS),
                        "source_refs": ["notes/some.md"],
                        "revision_note": "revised after drift",
                    }
                ]
            },
        },
    )
    assert res["status"] == "completed"
    assert _fm(draft)["status"] == "draft"


def test_submit_does_not_resurrect_deprecated(tmp_path: Path):
    repo, _od, draft = _mk_skill_repo(tmp_path, status="deprecated")
    _call(
        repo,
        {
            "mode": "submit",
            "report": {
                "skills": [
                    {
                        "name": "fork-pr-conflict",
                        "action": "updated",
                        "description": "当合入 fork 来源的 PR 且状态冲突时执行 SOP",
                        "body": "\n".join(f"## {s}\n\nrevised" for s in _SECTIONS),
                        "source_refs": ["notes/some.md"],
                    }
                ]
            },
        },
    )
    assert _fm(draft)["status"] == "deprecated"


@pytest.mark.parametrize("status", ["draft", "stable", "deprecated"])
def test_parse_skill_frontmatter_reads_status(tmp_path: Path, status: str):
    d = tmp_path / "skills"
    path = _write_draft(d, "x", status)
    assert sm.parse_skill_frontmatter(path.read_text(encoding="utf-8"))["status"] == status
