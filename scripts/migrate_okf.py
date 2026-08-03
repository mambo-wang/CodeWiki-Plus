#!/usr/bin/env python3
"""OKF v0.2 migration for existing CodeWiki LLM Wikis.

One-shot, idempotent migration that brings an existing ``repowiki/`` output
directory into OKF v0.2 conformance (SPEC §11):

1. Every non-reserved ``.md`` under ``wiki/``, ``notes/`` and ``raw/sources/``
   gets parseable YAML frontmatter with a non-empty ``type``.
2. Missing OKF keys are patched additively (``type``, ``generated``,
   ``stale_after``); existing keys are never overridden.
3. Legacy note ``status`` values are mapped to the OKF lifecycle vocabulary:
   candidate→draft, confirmed→stable, rejected/superseded→deprecated.
4. The bundle-root ``wiki/index.md`` gets ``okf_version: "0.2"`` (the only
   frontmatter permitted on an index file, SPEC §12).

Usage:
    python scripts/migrate_okf.py <output_dir> [--dry-run] [--stale-days 90]

``<output_dir>`` is the repowiki output directory (the one containing
``wiki/`` and ``schema.yaml``), e.g. ``./repowiki``.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)

RESERVED = {"index.md", "log.md"}

DIR_TYPE_MAP = {
    "modules": "Module",
    "entities": "Entity",
    "concepts": "Concept",
    "sources": "Source",
    "comparisons": "Comparison",
    "queries": "Query",
}

STATUS_MAP = {
    "candidate": "draft",
    "confirmed": "stable",
    "rejected": "deprecated",
    "superseded": "deprecated",
}


def split_frontmatter(content: str):
    """Return (fm_dict|None, fm_raw_lines, body_lines, end_idx)."""
    if not content.startswith("---"):
        return None, [], content.split("\n"), None
    lines = content.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_lines = lines[1:i]
            try:
                data = yaml.safe_load("\n".join(fm_lines))
                if not isinstance(data, dict):
                    data = None
            except Exception:
                data = None
            return data, fm_lines, lines[i + 1:], i
    return None, [], lines, None


def actor_id() -> str:
    try:
        from codewiki.src.config import actor_id as _aid
        return _aid()
    except Exception:
        return "codewiki"


def infer_type(path: Path, output_dir: Path) -> str:
    rel_parts = path.relative_to(output_dir).parts
    if path.name == "overview.md":
        return "Architecture"
    for part in rel_parts[:-1]:
        if part in DIR_TYPE_MAP:
            return DIR_TYPE_MAP[part]
    if "notes" in rel_parts[:-1]:
        return "Note"
    return "Concept"


def title_of(body_lines, fallback: str) -> str:
    for line in body_lines:
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def migrate_file(path: Path, output_dir: Path, stale_days: int, dry_run: bool) -> list:
    """Migrate one markdown file. Returns list of change descriptions."""
    changes = []
    content = path.read_text(encoding="utf-8")
    data, fm_lines, body_lines, end_idx = split_frontmatter(content)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale_date = (datetime.now(timezone.utc) + timedelta(days=stale_days)).strftime("%Y-%m-%d")
    actor = actor_id()

    additions = []

    if data is None and end_idx is None and not content.startswith("---"):
        # No frontmatter at all → create a minimal block
        doc_type = infer_type(path, output_dir)
        title = title_of(body_lines, path.stem)
        additions = [
            "---",
            f"type: {doc_type}",
            f'title: "{title}"',
            f"generated: {{ by: {actor}, at: {now_iso} }}",
            f"stale_after: {stale_date}",
            "---",
            "",
        ]
        new_content = "\n".join(additions) + content
        changes.append(f"created frontmatter (type: {doc_type})")
        if not dry_run:
            path.write_text(new_content, encoding="utf-8")
        return changes

    if data is None:
        # Starts with '---' but unparseable/unclosed → leave untouched
        changes.append("SKIPPED: unparseable frontmatter")
        return changes

    patch = []
    if not data.get("type"):
        doc_type = infer_type(path, output_dir)
        patch.append(f"type: {doc_type}")
        changes.append(f"patched type: {doc_type}")
    if "generated" not in data:
        patch.append(f"generated: {{ by: {actor}, at: {now_iso} }}")
        changes.append("patched generated")
    if "stale_after" not in data:
        patch.append(f"stale_after: {stale_date}")
        changes.append("patched stale_after")

    # Legacy status vocabulary → OKF lifecycle (notes and docs alike)
    status = data.get("status")
    if isinstance(status, str) and status in STATUS_MAP:
        new_status = STATUS_MAP[status]
        for j, line in enumerate(fm_lines):
            if re.match(r"^status:\s*\S+", line):
                fm_lines[j] = f"status: {new_status}"
                break
        changes.append(f"status: {status} → {new_status}")

    if patch:
        lines = content.split("\n")
        head = "\n".join(lines[:end_idx]).rstrip("\n")
        tail = "\n".join(lines[end_idx:])
        new_content = head + "\n" + "\n".join(patch) + "\n" + tail
        # re-apply status edits (fm_lines was mutated but content rebuilt from
        # original lines, so redo status substitution on the new string)
        if any(c.startswith("status:") for c in changes):
            for old, new in STATUS_MAP.items():
                new_content = re.sub(
                    rf"^(status:\s*){old}(\s*)$",
                    rf"\g<1>{new}\g<2>",
                    new_content, count=1, flags=re.MULTILINE,
                )
        if not dry_run:
            path.write_text(new_content, encoding="utf-8")
        return changes

    # Only status may have changed
    if changes:
        new_content = "\n".join(["---"] + fm_lines + ["---"] + body_lines)
        if not dry_run:
            path.write_text(new_content, encoding="utf-8")
    return changes


def ensure_okf_version(index_path: Path, dry_run: bool) -> bool:
    """Ensure bundle-root index.md declares okf_version (SPEC §12)."""
    content = index_path.read_text(encoding="utf-8")
    data, fm_lines, body_lines, end_idx = split_frontmatter(content)
    if isinstance(data, dict) and str(data.get("okf_version", "")) == "0.2":
        return False
    if isinstance(data, dict):
        if "okf_version" not in data:
            fm_lines.append('okf_version: "0.2"')
        new_content = "\n".join(["---"] + fm_lines + ["---"] + body_lines)
    else:
        new_content = '---\nokf_version: "0.2"\n---\n\n' + content
    if not dry_run:
        index_path.write_text(new_content, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Migrate a CodeWiki repowiki to OKF v0.2 conformance.")
    ap.add_argument("output_dir", help="repowiki output directory (contains wiki/ and schema.yaml)")
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    ap.add_argument("--stale-days", type=int, default=90, help="days until stale_after (default 90)")
    args = ap.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    wiki_dir = output_dir / "wiki"
    if not wiki_dir.is_dir():
        print(f"ERROR: {wiki_dir} not found — is this a repowiki output directory?", file=sys.stderr)
        return 1

    targets = []
    for p in sorted(wiki_dir.rglob("*.md")):
        if p.name not in RESERVED:
            targets.append(p)
    notes_dir = output_dir / "notes"
    if notes_dir.is_dir():
        targets.extend(sorted(notes_dir.rglob("*.md")))
    raw_sources = output_dir / "raw" / "sources"
    if raw_sources.is_dir():
        targets.extend(sorted(raw_sources.rglob("*.md")))

    changed = 0
    for path in targets:
        changes = migrate_file(path, output_dir, args.stale_days, args.dry_run)
        if changes:
            changed += 1
            rel = path.relative_to(output_dir)
            print(f"{'[dry-run] ' if args.dry_run else ''}{rel}: {'; '.join(changes)}")

    # Bundle-root index.md okf_version (wiki/index.md is the bundle entry)
    index_path = wiki_dir / "index.md"
    if index_path.is_file() and ensure_okf_version(index_path, args.dry_run):
        changed += 1
        print(f"{'[dry-run] ' if args.dry_run else ''}wiki/index.md: okf_version: \"0.2\"")

    print(f"\nScanned {len(targets)} files, {'would change' if args.dry_run else 'changed'} {changed}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
