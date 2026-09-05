"""Deterministic document similarity for ingest_source sibling detection.

Answers one question without calling any LLM: *does this document look like a
revised edition of something already imported?*  Per CodeWiki doctrine the tool
stays stateless — it reports a score and the evidence, and the caller (user)
makes the call.

Two signals, all dependency-free:

* **body** — Jaccard over character 3-gram shingles, estimated with a
  bottom-k MinHash sketch (the K smallest shingle hashes). CJK text has no
  whitespace word boundaries, so character n-grams beat word tokens here.
  An edited edition keeps most of its prose → high Jaccard. Template
  documents that merely share a skeleton and a topic (yearly reports) keep
  almost none of their shingles → low Jaccard.  **Body decides.**
* **skeleton** — Jaccard over the markdown heading sequence. Evidence for the
  caller and at most a +0.1 nudge — never decisive, because genuinely
  distinct template pages share skeletons.

Cost: one hash pass over the new document (shingles are sub-sampled), then
set intersections against registered sketches — microseconds per comparison.

Thresholds are deliberately skewed toward "ask the user": a false positive
costs one extra question, a false negative silently pollutes retrieval with a
twin document that has to be hunted down and cleaned up later.
"""

from __future__ import annotations

import hashlib
import heapq
import re
from typing import Any, Dict, List, Optional, Sequence

SIMILAR_HIGH = 0.50
SIMILAR_LOW = 0.25

_SHINGLE_N = 3
# Sub-sample cap: keeps the O(n) pass bounded on large documents.
_MAX_SHINGLES = 8000
# Bottom-k sketch size; ~sqrt(1/K) relative error on the Jaccard estimate.
_SKETCH_K = 128
_MAX_HEADINGS = 50
_MAX_HEADING_LEN = 80

_FENCE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# Keep CJK, latin letters and digits; drop punctuation/whitespace so that
# re-wrapping or re-punctuating a document does not change its fingerprint.
_NOISE_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def _strip_fences(text: str) -> str:
    """Blank out fenced code blocks so code/comments do not skew the signal."""
    return _FENCE_RE.sub(" ", text)


def extract_headings(text: str) -> List[str]:
    """Markdown heading texts, fences excluded, in document order."""
    stripped = _strip_fences(text)
    out: List[str] = []
    for match in _HEADING_RE.finditer(stripped):
        title = match.group(1).strip()
        if title:
            out.append(title[:_MAX_HEADING_LEN])
        if len(out) >= _MAX_HEADINGS:
            break
    return out


def _normalize(text: str) -> str:
    # Headings are already their own signal (the skeleton); dropping them from
    # the body keeps a shared document title from inflating the body Jaccard.
    return _NOISE_RE.sub("", _HEADING_RE.sub(" ", _strip_fences(text)))


def _shingles(normalized: str) -> List[str]:
    """Character n-grams, uniformly sub-sampled when the document is large."""
    total = len(normalized) - _SHINGLE_N + 1
    if total <= 0:
        return [normalized] if normalized else []
    if total <= _MAX_SHINGLES:
        return [normalized[i : i + _SHINGLE_N] for i in range(total)]
    step = total / _MAX_SHINGLES
    idx = 0.0
    out: List[str] = []
    for _ in range(_MAX_SHINGLES):
        start = int(idx)
        out.append(normalized[start : start + _SHINGLE_N])
        idx += step
    return out


def _hash64(token: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
    )


def _bottom_k(hashes: Sequence[int], k: int) -> List[int]:
    """The k smallest hashes — the bottom-k MinHash sketch."""
    if not hashes:
        return []
    if len(hashes) <= k:
        return sorted(hashes)
    return heapq.nsmallest(k, hashes)


def compute_fingerprint(text: str) -> Dict[str, Any]:
    """Fingerprint a document: bottom-k body sketch + heading skeleton + size."""
    normalized = _normalize(text)
    shingles = _shingles(normalized)
    if shingles:
        sketch = _bottom_k([_hash64(s) for s in shingles], _SKETCH_K)
    else:
        sketch = []
    return {
        "sketch": [f"{h:016x}" for h in sketch],
        "headings": extract_headings(text),
        "char_count": len(normalized),
        "shingle_count": len(shingles),
    }


def _sketch_jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    """Jaccard estimated from two hex bottom-k sketches."""
    set_a = set(left)
    set_b = set(right)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return len(set_a & set_b) / union


def _jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    set_a = {re.sub(r"\s+", "", h).lower() for h in left}
    set_b = {re.sub(r"\s+", "", h).lower() for h in right}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def body_similarity(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> float:
    """Body-signal only (sketch Jaccard). Decisive for well-sized documents."""
    if not left or not right:
        return 0.0
    return _sketch_jaccard(left.get("sketch") or [], right.get("sketch") or [])


def skeleton_similarity(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> float:
    """Heading-skeleton Jaccard only. Evidence, and decisive for short docs."""
    if not left or not right:
        return 0.0
    return _jaccard(left.get("headings") or [], right.get("headings") or [])


def similarity(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> float:
    """Blended similarity in [0, 1].

    Model: **body decides at any size**, skeleton nudges by at most 0.1. Body
    is the fraction of prose the two documents actually share, so an edited
    edition scores high while a template-only or title-only resemblance scores
    near zero. Body stays reliable on short documents because headings — which
    are the part most likely to coincide — are excluded from the body signal.
    """
    if not left or not right:
        return 0.0
    body = body_similarity(left, right)
    skeleton = skeleton_similarity(left, right)
    # Cap the boost so a shared skeleton can never carry an unrelated pair over
    # a threshold on its own.
    boost = 0.1 * skeleton if skeleton >= 0.5 and body >= 0.15 else 0.0
    return round(min(1.0, body + boost), 4)


def shared_headings(left: Optional[Dict], right: Optional[Dict], limit: int = 8) -> List[str]:
    """Headings present in both documents — the human-readable evidence."""
    if not left or not right:
        return []
    set_a = {re.sub(r"\s+", "", h).lower() for h in (left.get("headings") or [])}
    out: List[str] = []
    for heading in right.get("headings") or []:
        if re.sub(r"\s+", "", heading).lower() in set_a:
            out.append(heading)
        if len(out) >= limit:
            break
    return out


def classify(score: float) -> str:
    """'high' (confident sibling) / 'low' (suspected) / 'none' (unrelated)."""
    if score >= SIMILAR_HIGH:
        return "high"
    if score >= SIMILAR_LOW:
        return "low"
    return "none"
