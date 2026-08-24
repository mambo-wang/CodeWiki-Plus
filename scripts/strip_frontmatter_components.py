#!/usr/bin/env python3
"""One-off migration: strip `metadata.components` id lists from wiki pages.

The full component-id lists in frontmatter have no code consumer (retrieval,
lint, and reading-guide all resolve components via module_tree + SQLite
index) and large modules blow up the frontmatter by several KB of context
noise. This rewrites every page's `metadata.components` into
`metadata.component_count` (keeping an existing count if present).

Idempotent: files without a `components:` list under metadata are skipped.
Byte-safe on Windows: preserves original line endings (CRLF/LF/mixed).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Matches the `  components: [...]` metadata line (2-space indent, folded
# flow list possibly spanning multiple physical lines until the closing `]`).
_COMPONENTS_RE = re.compile(
    r"^(?P<indent>[ \t]+)components:[ \t]*\[(?P<body>(?:[^\[\]]|\n(?![ \t]*\S))*?)\][ \t]*(?P<eol>\r?\n)",
    re.MULTILINE,
)


def _count_ids(body: str) -> int:
    return len([p for p in body.split(",") if p.strip().strip("'\"")])


def migrate_file(path: Path) -> tuple[bool, int]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    m = _COMPONENTS_RE.search(text)
    if not m:
        return False, 0
    count = _count_ids(m.group("body"))
    indent, eol = m.group("indent"), m.group("eol")
    # Drop the components line, then drop ANY existing component_count line
    # within the same metadata block (the agent-written count may be stale —
    # e.g. 61 recorded for a 43-entry list), and insert the computed count.
    tail = text[m.end() :]
    count_line = f"{indent}component_count: {count}{eol}"
    # Remove a count line immediately following the components line.
    tail = re.sub(r"^\s*component_count:[^\r\n]*\r?\n", "", tail, count=1)
    replacement = count_line
    new_text = text[: m.start()] + replacement + tail
    # Remove any earlier duplicate count line inside the metadata block
    # (appearing before the components line).
    head = new_text[: m.start()]
    head = re.sub(
        r"^(?P<i>[ \t]+)component_count:[^\r\n]*\r?\n",
        "",
        head,
        flags=re.MULTILINE,
    )
    new_text = head + new_text[m.start() :]
    if new_text == text:
        return False, 0
    path.write_bytes(new_text.encode("utf-8"))
    return True, count


def main(repo_root: str) -> int:
    wiki = Path(repo_root) / "repowiki" / "wiki"
    changed = 0
    for md in wiki.rglob("*.md"):
        try:
            did, count = migrate_file(md)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {md}: {exc}")
            continue
        if did:
            changed += 1
            print(f"stripped {count:3d} ids  {md.relative_to(wiki)}")
    print(f"\n{changed} file(s) migrated")
    return 0


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(main(root))
