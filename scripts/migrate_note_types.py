#!/usr/bin/env python3
"""migrate_note_types — V4 存量 schema.yaml 幂等回填 note_types 权威表.

Usage (from the target repo root):
    python scripts/migrate_note_types.py [repowiki_dir]

Reads the authoritative table (codewiki.mcp.tools.note_types) and inserts a
``conventions.note_types`` section into ``<repowiki>/schema.yaml`` when absent
(existing tables are left untouched — idempotent).  Uses ruamel round-trip so
comments survive.  Run twice: the second run must be a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path


def migrate(repowiki: Path) -> int:
    schema_path = repowiki / "schema.yaml"
    if not schema_path.is_file():
        print(f"skip: {schema_path} not found")
        return 1

    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(schema_path)
    if not isinstance(data, dict):
        print(f"skip: {schema_path} is not a mapping")
        return 1

    conv = data.get("conventions")
    if not isinstance(conv, dict):
        print("skip: schema has no conventions section")
        return 1

    if isinstance(conv.get("note_types"), dict) and conv["note_types"]:
        print("ok: conventions.note_types already present (no-op)")
        return 0

    from codewiki.mcp.tools.note_types import DEFAULT_NOTE_TYPES

    conv["note_types"] = {t: dict(spec) for t, spec in DEFAULT_NOTE_TYPES.items()}
    with open(schema_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    print(f"ok: note_types table written into {schema_path}")
    return 0


def main(argv: list[str]) -> int:
    # Allow running from a source checkout without installing.
    repo_root = Path(__file__).resolve().parents[1]
    if repo_root not in sys.path:
        sys.path.insert(0, str(repo_root))
    target = Path(argv[1]) if len(argv) > 1 else repo_root / "repowiki"
    return migrate(target)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
