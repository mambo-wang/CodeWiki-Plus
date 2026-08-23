#!/usr/bin/env python3
"""backfill_description — V2 前置：存量 wiki 文档 description 幂等回填.

Usage (from the CodeWiki-CN source root):
    python scripts/backfill_description.py [repowiki_dir]

Rule-extracts the lede (first paragraph before the first ``## `` heading,
≤2 sentences, ≤160 chars) into the existing OKF ``description`` frontmatter
key.  Files that already carry a description (or have no frontmatter / no
extractable lede) are left byte-identical.  Run twice: the second run must
report written=0.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from codewiki.mcp.tools.doc_description import backfill_dir

    target = Path(argv[1]) if len(argv) > 1 else repo_root / "repowiki"
    stats = backfill_dir(target)
    print(
        f"backfill complete: written={stats['written']} "
        f"skipped={stats['skipped']} total={stats['total']} (under {target})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
