#!/usr/bin/env python3
"""One-off migration: backfill missing ``aliases`` in wiki page frontmatter.

Scans ``wiki/**/*.md`` under the given output dir.  For every page whose
frontmatter lacks an ``aliases:`` key, inject ``aliases: [<title>]``
(fallback: filename stem).  Body text is never touched; writes are atomic
(tmp file + os.replace) to avoid partial files.

Usage::

    python scripts/backfill_aliases.py [OUTPUT_DIR]

Default OUTPUT_DIR is ``repowiki`` relative to the repo root.

This is a data-fix script only.  Future generated pages already carry
``aliases`` (see doc_writer._build_okf_frontmatter /
_inject_lightweight_frontmatter and wiki_index.rebuild_index), so this does
not need to run again.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _split_frontmatter(content: str) -> tuple[str | None, str | None]:
    """Return (frontmatter_text, body) if frontmatter present, else (None, None)."""
    if not content.startswith("---"):
        return None, None
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, None
    return match.group(1), content[match.end() :]


def _has_aliases(fm_text: str) -> bool:
    try:
        data = yaml.safe_load(fm_text)
    except Exception:
        return False
    return isinstance(data, dict) and "aliases" in data


def backfill_file(path: Path) -> bool:
    """Add ``aliases: [<title>]`` to *path* if missing.  Returns True if written."""
    content = path.read_text(encoding="utf-8")
    fm_text, body = _split_frontmatter(content)
    if fm_text is None:
        return False
    if _has_aliases(fm_text):
        return False

    try:
        data = yaml.safe_load(fm_text)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False

    title = data.get("title") or path.stem
    aliases = [title] if isinstance(title, str) else [path.stem]
    alias_line = f"aliases: [{', '.join('"' + a.replace('"', '\\\\"') + '"' for a in aliases)}]"

    lines = fm_text.split("\n")
    # Insert right after the opening delimiter block (end of first non-empty
    # line group) — simplest robust spot is right before the closing '---',
    # i.e. append to frontmatter block in place.
    new_fm = "\n".join(lines + [alias_line])
    new_content = f"---\n{new_fm}\n---{body}"

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=path.stem + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return True


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "repowiki"
    wiki_dir = output_dir / "wiki"
    if not wiki_dir.is_dir():
        print(f"no wiki dir at {wiki_dir}", file=sys.stderr)
        return 1

    changed: list[Path] = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if not md_file.is_file():
            continue
        if backfill_file(md_file):
            changed.append(md_file)

    for p in changed:
        print(f"backfilled {p.relative_to(output_dir)}")
    print(f"\n{len(changed)} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
