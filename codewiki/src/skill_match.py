"""Draft-skill matching and skill-material scoring (skill-creator §10).

Stdlib-only by design: the IDE hook must import this without the package's
third-party deps (same constraint as ``codewiki.src.tool_digest``). Both
consumers share it so "is there a skill for this?" has ONE implementation:

- ``codewiki.mcp._ide_hook`` — UserPromptSubmit: match the user's prompt
  against uninstalled draft skills and inject a pointer.
- ``codewiki.mcp.tools.note_consolidation`` — L2 submit: score a freshly
  consolidated scenario for "is this behaviour instructions or reference
  knowledge?".
- ``codewiki.mcp.tools.distill_conversation`` — submit: match newly created
  note titles against draft skills.

Design decisions (grill 2026-09-07, see docs/skill-creator需求与设计方案.md §10):

- Only ``status == "draft"`` skills are matchable. ``install`` flips the draft
  to ``stable`` (it is no longer an uninstalled draft); a later ``submit``
  revision flips it back to ``draft`` because the effect-zone copy is now
  stale and the user should be prompted to reinstall.
- Matching NEVER returns the skill body — ``name`` + ``description`` only.
  ADR-0004 decision 2: the draft zone is indexed but not recallable; surfacing
  SKILL bodies would blur "retrieval knowledge" vs "behaviour instruction".
- Material scoring uses command density, NOT structure. Measured on the 8
  existing L2 scenarios: all 8 share the identical six-section skeleton and
  all have 5-11 numbered steps (zero discriminative power), while the single
  scenario that was actually compiled into a skill scored 11 command hits vs
  <= 2 for every other one. Section presence and step count are therefore
  useless as signals; executable-command density is the discriminator.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

# Containment cutoff for prompt <-> draft-skill matching.
#
# CONTAINMENT, NOT JACCARD — measured, not assumed: a prompt that is a verbatim
# prefix of the skill description (a perfect match, i.e. the upper bound)
# scores only 0.205 Jaccard, because the long description inflates the union.
# A 0.6 Jaccard gate would therefore NEVER fire. Containment (|A∩B| / min)
# scores the same pair 1.0. Threshold 0.5 = "half the prompt's tokens show up
# in the skill". Tuned by judgement (only 2 sample skills existed); re-evaluate
# de-duplication when the draft zone grows past ~5 skills.
DEFAULT_MATCH_THRESHOLD = 0.5

# A prompt shorter than this cannot be judged — "继续" / "ok" would otherwise
# match anything sharing a couple of bigrams.
MIN_PROMPT_TOKENS = 8

# Command hits (see ``_CMD_RE``) needed before an L2 scenario is worth
# suggesting as skill material. Positive example scored 11; the highest
# negative scored 2 — 3 sits just above the negatives with margin.
DEFAULT_CMD_THRESHOLD = 3

# Minimum ``notes/`` back-references. A scenario backed by a single note is
# usually a one-off, not a repeatable procedure.
DEFAULT_MIN_NOTE_REFS = 2

# Command-position biased: the trailing whitespace keeps prose mentions of
# e.g. "git" from counting as an executed step.
_CMD_RE = re.compile(
    r"(?i)\b(?:git|gh|uv|pytest|python|npm|npx|pnpm|curl|grep|rg|sed|awk|"
    r"find|docker|make|psql|jq)\s"
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_ASCII_RE = re.compile(r"[a-z0-9][a-z0-9_.\-]*")

# Event names (lower-cased) that carry a user prompt rather than a transcript.
PROMPT_EVENTS = frozenset({"userpromptsubmit"})


def tokenize(text: str) -> set:
    """Mixed CJK/ASCII tokenizer.

    ASCII runs become word tokens; CJK runs are sliced into character bigrams
    (no word boundaries exist in Chinese, and bigrams give Jaccard something
    to work with on short prompts).
    """
    lowered = (text or "").lower()
    tokens = set(_ASCII_RE.findall(lowered))
    cjk = "".join(_CJK_RE.findall(lowered))
    if len(cjk) == 1:
        tokens.add(cjk)
    for i in range(len(cjk) - 1):
        tokens.add(cjk[i : i + 2])
    return tokens


def containment(a: set, b: set) -> float:
    """Overlap coefficient: |A∩B| / min(|A|, |B|).

    Chosen over Jaccard for prompt↔description matching — see
    ``DEFAULT_MATCH_THRESHOLD`` for the measurement that ruled Jaccard out.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def parse_skill_frontmatter(text: str) -> Dict[str, str]:
    """Read only top-level ``key: value`` lines from a SKILL.md frontmatter.

    Deliberately not a general YAML parser: the hook path is stdlib-only and
    we need exactly three fields (name / description / status). Nested blocks
    (metadata.*) are skipped.
    """
    out: Dict[str, str] = {}
    if not text.startswith("---"):
        return out
    end = text.find("\n---", 3)
    if end == -1:
        return out
    for line in text[3:end].splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in " \t-#":
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            out[key.strip()] = value
    return out


def iter_draft_skills(skills_dir: str) -> List[Dict[str, str]]:
    """Draft-zone skills that are NOT installed yet (``status == draft``).

    Installed drafts are ``stable`` and therefore excluded — prompting the
    user to install an already-installed skill is pure noise (this was the
    entire population when the mechanism first shipped: 1 draft, already
    installed).
    """
    out: List[Dict[str, str]] = []
    if not skills_dir or not os.path.isdir(skills_dir):
        return out
    for entry in sorted(os.listdir(skills_dir)):
        path = os.path.join(skills_dir, entry, "SKILL.md")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        fm = parse_skill_frontmatter(text)
        if str(fm.get("status") or "draft").lower() != "draft":
            continue
        out.append(
            {
                "name": fm.get("name") or entry,
                "description": fm.get("description") or "",
                "file": f"skills/{entry}/SKILL.md",
            }
        )
    return out


def match_draft_skills(
    prompt: str,
    skills_dir: str,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> Optional[Dict[str, Any]]:
    """Best draft skill for ``prompt``, or None. Never returns the body."""
    p_tokens = tokenize(prompt)
    if len(p_tokens) < MIN_PROMPT_TOKENS:
        return None
    best: Optional[Dict[str, Any]] = None
    for skill in iter_draft_skills(skills_dir):
        s_tokens = tokenize(skill["name"] + " " + skill["description"])
        if not s_tokens:
            continue
        score = containment(p_tokens, s_tokens)
        if score < threshold:
            continue
        if best is None or score > best["score"]:
            best = {
                "name": skill["name"],
                "description": skill["description"],
                "file": skill["file"],
                "score": round(score, 3),
            }
    return best


def score_skill_material(
    text: str,
    cmd_threshold: int = DEFAULT_CMD_THRESHOLD,
    min_note_refs: int = DEFAULT_MIN_NOTE_REFS,
    kind: str = "scenario",
    note_type: str = "",
) -> Dict[str, Any]:
    """Does this material read as behaviour instructions rather than knowledge?

    Command density is the discriminator for scenarios (see module docstring
    for the measurement that ruled out section presence and step count).

    Notes use a different rule (2026-09-10): a note cannot self-reference
    ``notes/``, so ``min_note_refs`` is meaningless for it; the note TYPE
    carries the signal instead — ``procedure`` means "a reusable multi-step
    sequence", which is precisely skill material.

    Notes are the PRIMARY material, scenarios the secondary one: a scenario
    is already an aggregated, size-capped artefact where step order and
    checkpoints get flattened into single lines, while a note holds the
    sequence at original granularity.
    """
    body = text or ""
    cmd_hits = len(_CMD_RE.findall(body))
    code_blocks = body.count("```") // 2
    notes_refs = len(re.findall(r"notes/", body))
    already_compiled = "compiled_into" in body
    ntype = str(note_type or "").strip().lower()
    if kind == "note":
        procedural = ntype == "procedure"
        worth = bool((procedural or cmd_hits >= cmd_threshold) and not already_compiled)
    else:
        worth = bool(
            cmd_hits >= cmd_threshold
            and not already_compiled
            and notes_refs >= min_note_refs
        )
    return {
        "kind": kind,
        "note_type": ntype,
        "cmd_hits": cmd_hits,
        "code_blocks": code_blocks,
        "notes_refs": notes_refs,
        "already_compiled": already_compiled,
        "cmd_threshold": cmd_threshold,
        "worth_compiling": worth,
    }


def build_skill_hint(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build the additive ``skill_hint`` object.

    Two shapes:

    - ``kind="match"`` — an existing draft skill seems applicable to what the
      user is doing / just produced.
    - ``kind="material"`` — a fresh L2 scenario looks like skill material.

    Both are HINTS ONLY: never compile, never install, never write. The
    message is phrased as an executable instruction because hook-injected
    ``additionalContext`` is a soft constraint (see notes/2026-08-15-...).
    """
    if kind == "match":
        name = str(payload.get("name") or "")
        description = str(payload.get("description") or "")
        return {
            "skill_hint": {
                "kind": "match",
                "name": name,
                "description": description,
                "file": payload.get("file"),
                "score": payload.get("score"),
                "message": (
                    f"适用技能草稿 `{name}`：{description}\n"
                    f"如需启用：skill_creator(mode=\"install\", name=\"{name}\")\n"
                    "（需你确认后执行；我不会自动 install）"
                ),
            }
        }
    if kind == "material":
        rel = str(payload.get("file") or "")
        score = payload.get("score") if isinstance(payload.get("score"), dict) else {}
        is_note = payload.get("kind") == "note"
        label = "笔记" if is_note else "场景块"
        sources_arg = "notes" if is_note else "scenarios"
        if score.get("note_type") == "procedure":
            detail = "类型为 procedure（可复用的多步动作序列）"
        else:
            detail = (
                f"命令密度为 {score.get('cmd_hits', 0)}"
                f"（阈值 {score.get('cmd_threshold', DEFAULT_CMD_THRESHOLD)}）"
            )
        return {
            "skill_hint": {
                "kind": "material",
                "file": rel,
                "score": score,
                "message": (
                    f"{label} `{rel}` {detail}，"
                    "读起来像可执行的行为指令而非参考知识，可能值得编译成技能。\n"
                    f"如需评估：skill_creator(mode=\"prepare\", sources=[\"{sources_arg}\"])\n"
                    "（需你确认后执行；我不会自动编译）"
                ),
            }
        }
    return {}
