#!/usr/bin/env python3
"""Phase 0 baseline: golden snapshot of query_wiki retrieval paths.

Builds a fixed fixture wiki, runs both retrieval paths (legacy JSON index
and SQLite via build_full_index → search), and snapshots top-k order,
scores, authority, usage, est_tokens. Saved to a JSON file for later
field-by-field diff after each refactor phase.

Usage:
    python3 tests/golden_retrieval_baseline.py record <output.json>
    python3 tests/golden_retrieval_baseline.py diff <baseline.json> [<current.json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from codewiki.mcp.tools.wiki_search import build_full_index, search  # noqa: E402

FIXTURE = {
    "schema.yaml": """\
conventions:
  retrieval_cost:
    enabled: true
    chars_per_token: 4
""",
    "notes/2026-01-01-kernel-decision.md": """\
---
title: 检索 kernel 抽取决策
type: decision
status: stable
tags: [retrieval, kernel, BM25]
related_modules: [wiki_search]
description: 把 BM25 文本 kernel 从 cache.py 抽出为独立 deep module
---

# 检索 kernel 抽取决策

query_wiki 的检索路径需要一个小 interface 的 kernel。est_tokens 功能
落地时横穿了四个文件，根因是 kernel 没有自己的 interface。
""",
    "notes/2026-01-02-distill-pitfall.md": """\
---
title: 蒸馏重复笔记的坑
type: pitfall
status: draft
tags: [distill, dedup]
---

# 蒸馏重复笔记的坑

distill 的去重召回不应受 usage heat 影响，apply_usage=False 豁免。
""",
    "notes/2026-01-03-frontmatter-lesson.md": """\
---
title: frontmatter 解析多副本教训
type: lesson
status: stable
tags: [frontmatter, parser]
---

# frontmatter 解析多副本教训

五份手搓 parser 各自近似，语义漂移。应该统一走 src/frontmatter.py。
""",
    "wiki/modules/retrieval.md": """\
---
title: 检索模块
---

# 检索模块

BM25 检索 kernel、分词、authority 加权、usage heat。
SQLite 路径与 legacy JSON 路径双 adapter。
""",
    "wiki/scenarios/onboarding.md": """\
---
title: 新人上手场景
---

# 新人上手场景

先读 overview，再按模块检索。检索透明化提供 matched_tokens 与
query_coverage 缺失词提示。
""",
    "wiki/scenarios/daily-search.md": """\
---
title: 日常检索场景
---

# 日常检索场景

query_wiki 是高频入口。成本可见性 est_tokens 帮助决策是否展开。
""",
    "ontology.yaml": """\
terms:
  检索:
    aliases: [BM25, 搜索, retrieval]
""",
}

QUERIES = [
    ("检索 kernel", {}),
    ("BM25 分词", {}),
    ("kernel 抽取", {}),
    ("frontmatter", {}),
    ("蒸馏 去重", {}),
    ("检索", {"scope": "wiki"}),
    ("场景", {"scope": "wiki/scenarios"}),
    ("新人 上手", {}),
    ("检索 kernel", {"max_results": 3}),
    ("不存在的词xyzzy", {}),
]


def build_fixture(root: Path) -> Path:
    od = root / "repowiki"
    for rel, content in FIXTURE.items():
        p = od / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return od


def strip_floats(o):
    """Freeze floats to 6dp so repr noise never trips the diff."""
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, list):
        return [strip_floats(x) for x in o]
    if isinstance(o, dict):
        return {k: strip_floats(v) for k, v in o.items()}
    return o


def run_all(od: Path) -> dict:
    out = {}
    for qi, (query, kwargs) in enumerate(QUERIES):
        for path_name in ("json", "sqlite"):
            # fresh index per path so SQLite build does not influence the
            # JSON snapshot ordering (it doesn't share state, but be strict)
            results = search(
                od, query, session=None, expand_terms=None, chars_per_token=4, **kwargs
            )
            # search() with session=None may pick standalone SQLite if a DB
            # exists — for the JSON path we must point at a fixture without
            # any .codewiki dir; handled by caller via separate roots.
            out[f"q{qi:02d}:{path_name}:{query}"] = strip_floats(results)
    return out


def main():
    import tempfile

    mode = sys.argv[1] if len(sys.argv) > 1 else "record"
    out_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if mode == "record":
        assert out_file, "record needs <output.json>"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Path A: legacy JSON (no SQLite db anywhere)
            od_json = build_fixture(root / "a")
            # Path B: SQLite — build the index so analysis_cache.db exists
            od_sql = build_fixture(root / "b")
            build_full_index(od_sql)

            snap = {}
            for qi, (query, kwargs) in enumerate(QUERIES):
                r = search(od_json, query, session=None, chars_per_token=4, **kwargs)
                snap[f"q{qi:02d}:json"] = strip_floats(r)
                r = search(od_sql, query, session=None, chars_per_token=4, **kwargs)
                snap[f"q{qi:02d}:sqlite"] = strip_floats(r)
            out_file.write_text(
                json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True),
                encoding="utf-8",
            )
            n_hits = sum(len(v) for v in snap.values())
            print(f"recorded {len(snap)} query snapshots, {n_hits} total hits -> {out_file}")
    elif mode == "diff":
        assert out_file, "diff needs <baseline.json>"
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            cur = Path(td) / "current.json"
            subprocess.run(
                [sys.executable, __file__, "record", str(cur)], check=True
            )
            base = json.loads(out_file.read_text(encoding="utf-8"))
            now = json.loads(cur.read_text(encoding="utf-8"))
            if base == now:
                print("GOLDEN OK: no drift")
                return
            keys = sorted(set(base) | set(now))
            bad = 0
            for k in keys:
                if base.get(k) != now.get(k):
                    bad += 1
                    print(f"DRIFT at {k}:")
                    print("  baseline:", json.dumps(base.get(k), ensure_ascii=False)[:400])
                    print("  current :", json.dumps(now.get(k), ensure_ascii=False)[:400])
            print(f"GOLDEN FAIL: {bad}/{len(keys)} snapshots drifted")
            sys.exit(1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
