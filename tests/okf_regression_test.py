#!/usr/bin/env python3
"""OKF v0.2 适配回归测试 — 逐个覆盖受影响的 MCP 工具。

直接调用工作区代码（非已安装副本）：仓库根自动识别
（脚本位于 tests/ 时取其父目录，否则回退到开发检出路径），
在临时 bundle 上端到端验证每个受影响工具的行为。

运行: python okf_regression_test.py
"""

import asyncio
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml as _yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Repo root: prefer the repo this file lives in (tests/), fall back to the
# known development checkout when run from an external workspace.
_here = Path(__file__).resolve().parent
REPO = _here.parent if (_here.parent / "codewiki").is_dir() else Path(r"D:\repos\CodeWiki-CN")
sys.path.insert(0, str(REPO))

from codewiki.mcp.session import SessionStore  # noqa: E402
from codewiki.mcp.tools.doc_writer import (  # noqa: E402
    handle_edit_doc_file,
    handle_write_doc_file,
    _inject_lightweight_frontmatter,
)
from codewiki.mcp.tools.knowledge_loop import (  # noqa: E402
    handle_confirm_note,
    handle_ingest_note,
    handle_query_wiki,
    handle_reject_note,
    _extract_frontmatter,
)
from codewiki.mcp.tools.source_ingest import (  # noqa: E402
    handle_ingest_source,
    handle_retract_source,
)
from codewiki.mcp.tools.batch_ingest import handle_batch_ingest  # noqa: E402
from codewiki.mcp.tools.wiki_lint import handle_lint_wiki  # noqa: E402
from codewiki.mcp.tools.init_wiki import handle_init_wiki  # noqa: E402
from codewiki.mcp.tools.prompt_server import handle_get_prompt  # noqa: E402
from codewiki.mcp.tools.close_session import handle_close_session  # noqa: E402
from scripts.migrate_okf import migrate_file  # noqa: E402

_passed = 0
_failed = 0
_failures = []


def check(section: str, name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS: {name}")
    else:
        _failed += 1
        _failures.append(f"[{section}] {name} — {detail}")
        print(f"  FAIL: {name} — {detail[:300]}")


def read_fm(path: Path) -> str:
    """Return raw frontmatter text of a markdown file."""
    t = path.read_text(encoding="utf-8")
    if not t.startswith("---"):
        return ""
    end = t.find("---", 3)
    return t[3:end] if end > 0 else ""


def main():
    print("=== OKF v0.2 受影响 MCP 工具回归测试 ===\n")

    base = Path(tempfile.mkdtemp(prefix="okf_reg_")).resolve()
    output_dir = base / "repowiki"
    output_dir.mkdir(parents=True)
    fake_repo = base / "repo"
    fake_repo.mkdir()

    # Minimal schema with OKF v0.2 conventions
    (output_dir / "schema.yaml").write_text(
        'conventions:\n  okf_frontmatter: true\n  okf_version: "0.2"\n  default_stale_days: 90\n',
        encoding="utf-8",
    )

    store = SessionStore()
    session = store.create(str(fake_repo), str(output_dir), {}, [])
    sid = session.session_id

    # ================================================================
    print("[1] write_doc_file — OKF frontmatter 注入/补丁")
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_new.md",
                    "content": "# 新文档\n\n这是没有 frontmatter 的新文档。\n",
                },
                store,
            )
        )
    )
    doc1 = Path(r.get("path", ""))
    check("write_doc_file", "新文档创建成功", r.get("status") == "created", str(r)[:200])
    if doc1.exists():
        fm1 = read_fm(doc1)
        check("write_doc_file", "注入 type", "type:" in fm1, fm1[:200])
        check(
            "write_doc_file",
            "注入 generated",
            "generated:" in fm1 and "codewiki/" in fm1,
            fm1[:300],
        )
        check("write_doc_file", "注入 stale_after(90d)", "stale_after:" in fm1, fm1[:300])
        # 代码生成 wiki 场景默认 stable（OKF v0.2 生命周期）
        check("write_doc_file", "默认status=stable", "status: stable" in fm1, fm1[:300])
        check("write_doc_file", "status仅注入一次", fm1.count("status:") == 1, fm1[:300])

    # frontmatter_extra 显式 status 可覆盖默认 stable
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_draft_override.md",
                    "content": "# 覆盖测试\n\n显式指定 draft 状态。\n",
                    "frontmatter_extra": {"status": "draft"},
                },
                store,
            )
        )
    )
    over_doc = Path(r.get("path", ""))
    if over_doc.exists():
        over_fm = read_fm(over_doc)
        check(
            "write_doc_file",
            "frontmatter_extra可覆盖为draft",
            "status: draft" in over_fm,
            over_fm[:300],
        )
        check("write_doc_file", "覆盖时不重复注入", over_fm.count("status:") == 1, over_fm[:300])

    # Agent-written frontmatter without type → patched (P0 fix)
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_agent.md",
                    "content": "---\ntitle: 自定义标题\ncustom_key: keep-me\n---\n# 代理文档\n\n正文。\n",
                },
                store,
            )
        )
    )
    doc2 = Path(r.get("path", ""))
    if doc2.exists():
        fm2 = read_fm(doc2)
        check("write_doc_file", "已有frontmatter被补丁type", "type:" in fm2, fm2[:300])
        check("write_doc_file", "保留代理自定义键", "custom_key: keep-me" in fm2, fm2[:300])
        check("write_doc_file", "保留原标题", "自定义标题" in fm2, fm2[:300])
        check(
            "write_doc_file",
            "补丁generated/stale_after",
            "generated:" in fm2 and "stale_after:" in fm2,
            fm2[:400],
        )
        check("write_doc_file", "缺失status补丁为stable", "status: stable" in fm2, fm2[:400])

    # Agent-written frontmatter WITH type → untouched type, no dup
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_typed.md",
                    "content": "---\ntype: Concept\ntitle: 已有类型\n---\n# 已带类型\n\n正文。\n",
                },
                store,
            )
        )
    )
    doc3 = Path(r.get("path", ""))
    if doc3.exists():
        fm3 = read_fm(doc3)
        check(
            "write_doc_file",
            "已有type不重复注入",
            fm3.count("type:") == 1 and "Concept" in fm3,
            fm3[:300],
        )

    # ================================================================
    print("\n[2] edit_doc_file — frontmatter 存在时的编辑")
    r = json.loads(
        asyncio.run(
            handle_edit_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_new.md",
                    "command": "str_replace",
                    "old_string": "# 新文档",
                    "new_string": "# 新文档V2",
                },
                store,
            )
        )
    )
    check("edit_doc_file", "str_replace成功", r.get("status") == "edited", str(r)[:200])
    if doc1.exists():
        check(
            "edit_doc_file",
            "frontmatter未被破坏",
            doc1.read_text(encoding="utf-8").startswith("---"),
            "",
        )
        check("edit_doc_file", "正文已更新", "# 新文档V2" in doc1.read_text(encoding="utf-8"), "")

    # ================================================================
    print("\n[2b] doc_writer — frontmatter_extra 私有字段折叠 metadata")
    # session 模式：OKF 标准键留顶层，私有键(components/related_modules/date/severity/...)折叠
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_fold.md",
                    "content": "# 折叠测试\n\n正文内容。\n",
                    "frontmatter_extra": {
                        "components": ["AuthService", "OrderService"],
                        "related_modules": ["auth", "order"],
                        "date": "2026-08-01",
                        "severity": "high",
                        "status": "stable",
                        "category": "backend",
                    },
                },
                store,
            )
        )
    )
    fold_doc = Path(r.get("path", ""))
    if fold_doc.exists():
        fmf = read_fm(fold_doc)
        try:
            fold_y = _yaml.safe_load(fmf)
        except Exception as e:
            fold_y = {}
            print("  (fold yaml err:", e, ")")
        meta = fold_y.get("metadata") or {}
        check("doc_writer", "标准键status留在顶层", fold_y.get("status") == "stable", fmf[:400])
        check(
            "doc_writer",
            "components折叠进metadata",
            meta.get("components") == ["AuthService", "OrderService"],
            fmf[:600],
        )
        check(
            "doc_writer",
            "related_modules折叠进metadata",
            meta.get("related_modules") == ["auth", "order"],
            fmf[:600],
        )
        check("doc_writer", "date折叠进metadata", meta.get("date") == "2026-08-01", fmf[:600])
        check("doc_writer", "severity折叠进metadata", meta.get("severity") == "high", fmf[:600])
        check("doc_writer", "category折叠进metadata", meta.get("category") == "backend", fmf[:600])
        check(
            "doc_writer",
            "顶层无components",
            "components:" not in fmf.split("\nmetadata:")[0],
            fmf[:400],
        )

    # body 提取的 source_refs/chunk_refs 折叠进 metadata
    r = json.loads(
        asyncio.run(
            handle_write_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_srcfold.md",
                    "content": "# 来源折叠\n\n正文引用[^src:alpha:1-5]内容。\n",
                },
                store,
            )
        )
    )
    src_doc = Path(r.get("path", ""))
    if src_doc.exists():
        fms = read_fm(src_doc)
        try:
            src_y = _yaml.safe_load(fms)
        except Exception as e:
            src_y = {}
            print("  (src yaml err:", e, ")")
        src_meta = src_y.get("metadata") or {}
        check(
            "doc_writer",
            "source_refs折叠进metadata",
            "alpha" in (src_meta.get("source_refs") or []),
            fms[:600],
        )
        check(
            "doc_writer",
            "chunk_refs折叠进metadata",
            "alpha:1-5" in (src_meta.get("chunk_refs") or []),
            fms[:600],
        )
        check(
            "doc_writer",
            "顶层无source_refs",
            not any(ln.startswith("source_refs:") for ln in fms.splitlines()),
            fms[:400],
        )

    # edit 后 _resync_source_refs 保持折叠
    r = json.loads(
        asyncio.run(
            handle_edit_doc_file(
                {
                    "session_id": sid,
                    "filename": "okf_srcfold.md",
                    "command": "str_replace",
                    "old_string": "# 来源折叠",
                    "new_string": "# 来源折叠V2",
                },
                store,
            )
        )
    )
    if src_doc.exists():
        fme = read_fm(src_doc)
        check(
            "doc_writer",
            "edit后source_refs仍折叠(缩进)",
            any(
                ln.lstrip().startswith("source_refs:") and ln.startswith("  ")
                for ln in fme.splitlines()
            ),
            fme[:500],
        )
        check(
            "doc_writer",
            "edit后顶层无source_refs",
            not any(
                ln.strip().startswith("source_refs:")
                for ln in fme.splitlines()
                if not ln.startswith("  ")
            ),
            fme[:400],
        )

    # sessionless 模式 _inject_lightweight_frontmatter 同样折叠
    light = _inject_lightweight_frontmatter(
        "okf_light.md",
        "# 轻量\n\n正文。\n",
        page_type="module",
        frontmatter_extra={"components": ["X"], "status": "stable", "severity": "low"},
    )
    light_fm = light.split("---", 2)[1] if light.startswith("---") else ""
    try:
        light_y = _yaml.safe_load(light_fm)
    except Exception as e:
        light_y = {}
        print("  (light yaml err:", e, ")")
    check(
        "doc_writer",
        "sessionless标准键status顶层",
        light_y.get("status") == "stable",
        light_fm[:400],
    )
    light_meta = light_y.get("metadata") or {}
    check(
        "doc_writer",
        "sessionless components折叠",
        light_meta.get("components") == ["X"],
        light_fm[:500],
    )
    check(
        "doc_writer",
        "sessionless severity折叠",
        light_meta.get("severity") == "low",
        light_fm[:500],
    )

    # knowledge_loop._extract_frontmatter 支持 metadata 回退
    _fm_folded = (
        "---\ntype: note\ntitle: X\nmetadata:\n"
        '  origin: human\n  date: "2026-08-01"\n---\n\n正文。\n'
    )
    check(
        "doc_writer",
        "_extract_frontmatter读折叠origin",
        _extract_frontmatter(_fm_folded, "origin") == "human",
        _extract_frontmatter(_fm_folded, "origin") or "",
    )
    check(
        "doc_writer",
        "_extract_frontmatter读折叠date",
        _extract_frontmatter(_fm_folded, "date") == "2026-08-01",
        _extract_frontmatter(_fm_folded, "date") or "",
    )
    check(
        "doc_writer",
        "_extract_frontmatter顶层优先",
        _extract_frontmatter("---\ntitle: Y\norigin: top\n---\n\n正文。\n", "origin") == "top",
        "",
    )

    # ================================================================
    print("\n[2c] migrate_okf --fold-private — 行手术折叠且不churn未动键")
    mig_dir = base / "migrate_okf"
    mig_src = mig_dir / "wiki" / "modules"
    mig_src.mkdir(parents=True)
    mig_file = mig_src / "Legacy.md"
    mig_file.write_text(
        "---\n"
        "type: Module\n"
        'title: "Legacy"\n'
        "status: candidate\n"
        "generated: { by: human:alice, at: '2026-08-01T00:00:00Z' }\n"
        "related_modules:\n"
        "  - auth\n"
        "  - order\n"
        "severity: high\n"
        "date: 2026-08-01\n"
        "category: backend\n"
        'source_refs: ["README_CN"]\n'
        "---\n"
        "\n"
        "# Legacy\n\n正文。\n",
        encoding="utf-8",
    )
    mig_changes = migrate_file(mig_file, mig_dir, 90, False, True)
    mig_fm = read_fm(mig_file)
    check(
        "migrate_okf", "私有键已折叠", "folded metadata:" in " ".join(mig_changes), str(mig_changes)
    )
    check(
        "migrate_okf",
        "顶层无私有键",
        not any(
            ln.startswith(k + ":")
            for ln in mig_fm.splitlines()
            for k in ("related_modules", "severity", "date", "category", "source_refs")
        ),
        mig_fm[:400],
    )
    try:
        mig_y = _yaml.safe_load(mig_fm)
    except Exception as e:
        mig_y = {}
        print("  (migrate yaml err:", e, ")")
    mig_meta = mig_y.get("metadata") or {}
    check(
        "migrate_okf",
        "metadata含related_modules",
        mig_meta.get("related_modules") == ["auth", "order"],
        mig_fm[:600],
    )
    check("migrate_okf", "metadata含severity", mig_meta.get("severity") == "high", mig_fm[:600])
    check("migrate_okf", "metadata含date", mig_meta.get("date") == "2026-08-01", mig_fm[:600])
    check(
        "migrate_okf",
        "metadata含source_refs",
        mig_meta.get("source_refs") == ["README_CN"],
        mig_fm[:600],
    )
    check("migrate_okf", "未动键格式保持(title引号)", 'title: "Legacy"' in mig_fm, mig_fm[:300])
    check(
        "migrate_okf",
        "未动键格式保持(generated flow映射)",
        "generated: { by: human:alice" in mig_fm,
        mig_fm[:300],
    )
    check("migrate_okf", "status映射candidate→draft", mig_y.get("status") == "draft", mig_fm[:300])
    check(
        "migrate_okf",
        "折叠值为单行JSON(行式读取兼容)",
        any(ln.startswith("  source_refs: [") for ln in mig_fm.splitlines()),
        mig_fm[:400],
    )
    check("migrate_okf", "补丁键stale_after已补齐", "stale_after" in mig_fm, mig_fm[:300])
    mig_changes2 = migrate_file(mig_file, mig_dir, 90, False, True)
    check("migrate_okf", "幂等-二次运行无改动", not mig_changes2, str(mig_changes2))

    # ================================================================
    print("\n[3] ingest_note — 生命周期默认值与归一化")
    r = json.loads(
        handle_ingest_note(
            {
                "session_id": sid,
                "note_type": "decision",
                "title": "OKF回归测试决策",
                "content": "这是OKF回归测试的决策笔记内容。",
            },
            store,
        )
    )
    note1 = Path(r.get("note_path", ""))
    check("ingest_note", "默认status=draft", r.get("note_status") == "draft", str(r)[:200])
    check("ingest_note", "返回draft提示", "draft" in r.get("hint", ""), str(r.get("hint"))[:150])
    if note1.exists():
        fm = read_fm(note1)
        check("ingest_note", "写入generated", "generated:" in fm, fm[:300])
        check("ingest_note", "写入stale_after", "stale_after:" in fm, fm[:300])

    r = json.loads(
        handle_ingest_note(
            {
                "session_id": sid,
                "note_type": "lesson",
                "title": "显式stable笔记",
                "content": "这条笔记显式指定stable状态。",
                "status": "stable",
            },
            store,
        )
    )
    check("ingest_note", "显式status=stable接受", r.get("note_status") == "stable", str(r)[:200])

    r = json.loads(
        handle_ingest_note(
            {
                "session_id": sid,
                "note_type": "pitfall",
                "title": "旧词汇candidate笔记",
                "content": "这条笔记用旧词汇candidate。",
                "status": "candidate",
            },
            store,
        )
    )
    note3 = Path(r.get("note_path", ""))
    check(
        "ingest_note",
        "legacy candidate归一化为draft",
        r.get("note_status") == "draft",
        str(r)[:200],
    )

    # ================================================================
    print("\n[4] confirm_note — stable升级与verified事件")
    r = json.loads(
        handle_confirm_note(
            {
                "session_id": sid,
                "note_file": note1.name,
                "by": "human:tester",
            },
            store,
        )
    )
    check("confirm_note", "升级为stable", r.get("status") == "stable", str(r)[:200])
    fm = read_fm(note1)
    check(
        "confirm_note",
        "记录verified事件(human:tester)",
        "verified:" in fm and "human:tester" in fm,
        fm[:500],
    )
    import re as _re

    m = _re.search(r"stale_after:\s*['\"]?(\d{4}-\d{2}-\d{2})", fm)
    renewed = False
    if m:
        renewed = datetime.strptime(m.group(1), "%Y-%m-%d") > datetime.now() + timedelta(days=80)
    check("confirm_note", "stale_after已续期(~90d)", renewed, fm[:500])

    # Default actor when by is omitted
    r = json.loads(handle_confirm_note({"session_id": sid, "note_file": note3.name}, store))
    fm = read_fm(note3)
    check("confirm_note", "默认actor=codewiki", "codewiki/" in fm, fm[:500])

    # Legacy note: status confirmed + bare-mapping verified
    notes_dir = output_dir / "notes"
    legacy = notes_dir / "2020-01-01-legacy-note.md"
    legacy.write_text(
        "---\ntype: lesson\ntitle: 旧格式笔记\ndate: 2020-01-01\n"
        "status: confirmed\nverified: {by: human:old-reviewer, at: 2020-01-02T00:00:00Z}\n"
        "---\n\n旧格式正文。\n",
        encoding="utf-8",
    )
    r = json.loads(handle_confirm_note({"session_id": sid, "note_file": legacy.name}, store))
    fm = read_fm(legacy)
    check("confirm_note", "legacy confirmed→stable", r.get("status") == "stable", str(r)[:200])
    try:
        data = _yaml.safe_load(fm)
        vlist = data.get("verified")
        ok = (
            isinstance(vlist, list)
            and len(vlist) == 2
            and vlist[0].get("by") == "human:old-reviewer"
            and "codewiki/" in str(vlist[1].get("by", ""))
        )
    except Exception as e:
        ok, data = False, str(e)
    check("confirm_note", "bare verified映射转列表并追加", ok, str(data)[:300])

    # ================================================================
    print("\n[5] reject_note — deprecated标记")
    r = json.loads(
        handle_ingest_note(
            {
                "session_id": sid,
                "note_type": "general",
                "title": "待否决笔记",
                "content": "这条笔记将被否决。",
            },
            store,
        )
    )
    note4 = Path(r.get("note_path", ""))
    r = json.loads(
        handle_reject_note(
            {
                "session_id": sid,
                "note_file": note4.name,
                "reason": "回归测试否决",
            },
            store,
        )
    )
    check("reject_note", "标记deprecated", r.get("status") == "deprecated", str(r)[:200])
    fm = read_fm(note4)
    check("reject_note", "保留否决原因", "回归测试否决" in fm, fm[:400])

    # ================================================================
    print("\n[6] query_wiki — 读端状态归一化与过滤")
    # Legacy confirmed note (no verified list) written directly
    legacy2 = notes_dir / "2020-02-02-legacy-confirmed.md"
    legacy2.write_text(
        "---\ntype: decision\ntitle: 旧确认笔记\ndate: 2020-02-02\n"
        'status: confirmed\ntags: ["legacyquery"]\n---\n\n旧确认笔记正文 uniqueword-zeta。\n',
        encoding="utf-8",
    )
    try:
        from codewiki.mcp.tools.wiki_search import build_full_index

        build_full_index(output_dir, session=store.get(sid))
    except Exception as e:
        print("  (index rebuild warning:", e, ")")

    r = json.loads(
        handle_query_wiki(
            {
                "session_id": sid,
                "query": "legacyquery 旧确认笔记",
            },
            store,
        )
    )
    results = r.get("results", [])
    legacy_hits = [x for x in results if "旧确认笔记" in str(x.get("title", ""))]
    check("query_wiki", "legacy confirmed可检索", len(legacy_hits) > 0, str(results)[:300])
    if legacy_hits:
        check(
            "query_wiki",
            "legacy confirmed无[unconfirmed]前缀",
            "[unconfirmed]" not in legacy_hits[0].get("title", ""),
            str(legacy_hits[0])[:200],
        )

    r = json.loads(handle_query_wiki({"session_id": sid, "query": "待否决笔记"}, store))
    rej_hits = [x for x in r.get("results", []) if "待否决" in str(x.get("title", ""))]
    check("query_wiki", "deprecated笔记被过滤", len(rej_hits) == 0, str(r.get("results"))[:300])

    r = json.loads(handle_query_wiki({"session_id": sid, "query": "OKF回归测试决策"}, store))
    conf_hits = [x for x in r.get("results", []) if "OKF回归测试决策" in str(x.get("title", ""))]
    check("query_wiki", "stable笔记可检索", len(conf_hits) > 0, str(r.get("results"))[:300])
    if conf_hits:
        check(
            "query_wiki",
            "trust_tier=human-reviewed",
            conf_hits[0].get("trust_tier") == "human-reviewed",
            str(conf_hits[0])[:300],
        )

    # ================================================================
    print("\n[7] ingest_source — 外部文档登记与sources注入")
    src_file = base / "ext_spec.md"
    src_file.write_text("# 外部规范\n\n这是外部规范文档的正文内容。\n", encoding="utf-8")
    rel_target = doc1.as_posix().split("/repowiki/", 1)[1]
    r = json.loads(
        handle_ingest_source(
            {
                "session_id": sid,
                "source_ref": str(src_file),
                "name": "ext-spec",
                "source_type": "md",
                "description": "外部规范",
                "related_pages": [rel_target],
            },
            store,
        )
    )
    check("ingest_source", "登记成功", r.get("status") == "ingested", str(r)[:200])
    stored = output_dir / r.get("stored_at", "")
    check("ingest_source", "文件已入库", stored.exists(), str(stored))
    if stored.exists():
        fm = read_fm(stored)
        check(
            "ingest_source",
            "md源注入type/status/generated",
            "type:" in fm and "status:" in fm and "generated:" in fm,
            fm[:400],
        )
    fm1 = read_fm(doc1)
    check(
        "ingest_source",
        "相关页面注入sources条目",
        "sources:" in fm1 and "ext-spec" in fm1,
        fm1[:600],
    )

    r = json.loads(
        handle_ingest_source(
            {
                "session_id": sid,
                "source_ref": str(src_file),
                "name": "ext-spec-dup",
            },
            store,
        )
    )
    check("ingest_source", "重复内容检测", r.get("status") == "duplicate", str(r)[:200])

    # ================================================================
    print("\n[8] retract_source — dry_run与引用清理")
    r = json.loads(
        handle_retract_source(
            {
                "session_id": sid,
                "name": "ext-spec",
                "mode": "remove_refs",
                "dry_run": True,
            },
            store,
        )
    )
    check("retract_source", "dry_run返回预览", r.get("status") == "dry_run", str(r)[:200])
    check("retract_source", "dry_run预告清理refs", r.get("would_clean_refs", 0) >= 1, str(r)[:200])

    r = json.loads(
        handle_retract_source(
            {
                "session_id": sid,
                "name": "ext-spec",
                "mode": "remove_refs",
            },
            store,
        )
    )
    check("retract_source", "撤回成功", r.get("status") == "retracted", str(r)[:200])
    check("retract_source", "清理了页面sources引用", r.get("cleaned_refs", 0) >= 1, str(r)[:200])
    fm1 = read_fm(doc1)
    check("retract_source", "页面sources条目已移除", "ext-spec" not in fm1, fm1[:600])
    trash = list((output_dir / ".trash").glob("*")) if (output_dir / ".trash").exists() else []
    check("retract_source", "源文件移入.trash", len(trash) >= 1, str(trash)[:200])

    # ================================================================
    print("\n[9] batch_ingest — 批量笔记+源")
    src2 = base / "batch_doc.md"
    src2.write_text("# 批量文档\n\n批量导入测试内容。\n", encoding="utf-8")
    r = json.loads(
        handle_batch_ingest(
            {
                "session_id": sid,
                "items": [
                    {
                        "kind": "note",
                        "note_type": "general",
                        "title": "批量笔记一",
                        "content": "批量导入的笔记内容。",
                    },
                    {"kind": "source", "source_ref": str(src2), "name": "batch-doc"},
                ],
            },
            store,
        )
    )
    check("batch_ingest", "批量完成", r.get("status") == "completed", str(r)[:200])
    items = r.get("results", [])
    check(
        "batch_ingest",
        "2项全部ok",
        len(items) == 2 and all(i.get("status") == "ok" for i in items),
        str(items)[:300],
    )

    # ================================================================
    print("\n[10] lint_wiki — okf_conformance 检测能力")
    bad_dir = output_dir / "wiki" / "modules"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "bad_nofm.md").write_text("# 无frontmatter\n\n正文。\n", encoding="utf-8")
    (bad_dir / "bad_legacy.md").write_text(
        "---\ntype: Module\nstatus: confirmed\n---\n# 旧状态\n", encoding="utf-8"
    )
    (bad_dir / "bad_expired.md").write_text(
        "---\ntype: Module\nstale_after: 2020-01-01\n---\n# 过期\n", encoding="utf-8"
    )
    (bad_dir / "bad_verified.md").write_text(
        "---\ntype: Module\nverified: oops-not-a-list\n---\n# 坏verified\n", encoding="utf-8"
    )

    r = json.loads(handle_lint_wiki({"session_id": sid, "checks": ["all"]}, store))
    lint_data = json.loads(Path(r["file"]).read_text(encoding="utf-8")) if "file" in r else r
    checks_run = lint_data.get("checks_run", [])
    check("lint_wiki", "16项检查全跑", len(checks_run) == 16, str(checks_run))
    check("lint_wiki", "含okf_conformance", "okf_conformance" in checks_run, str(checks_run))
    okf_issues = [i for i in lint_data.get("issues", []) if i.get("check") == "okf_conformance"]
    kinds = {i.get("file", ""): i.get("message", "") for i in okf_issues}
    check(
        "lint_wiki",
        "检出无frontmatter(error)",
        any(i.get("severity") == "error" and "bad_nofm" in i.get("file", "") for i in okf_issues),
        str(kinds)[:300],
    )
    check(
        "lint_wiki",
        "检出legacy status(warning)",
        any(
            "bad_legacy" in i.get("file", "") and "Legacy status" in i.get("message", "")
            for i in okf_issues
        ),
        str(kinds)[:300],
    )
    check(
        "lint_wiki",
        "检出过期stale_after",
        any("bad_expired" in i.get("file", "") for i in okf_issues),
        str(kinds)[:300],
    )
    check(
        "lint_wiki",
        "检出坏verified",
        any("bad_verified" in i.get("file", "") for i in okf_issues),
        str(kinds)[:300],
    )

    for b in ("bad_nofm.md", "bad_legacy.md", "bad_expired.md", "bad_verified.md"):
        (bad_dir / b).unlink(missing_ok=True)
    r = json.loads(handle_lint_wiki({"session_id": sid, "checks": ["okf_conformance"]}, store))
    lint_data = json.loads(Path(r["file"]).read_text(encoding="utf-8")) if "file" in r else r
    errs = [i for i in lint_data.get("issues", []) if i.get("severity") == "error"]
    check("lint_wiki", "清理后0 error", len(errs) == 0, str(errs)[:300])

    # ================================================================
    print("\n[11] init_wiki — 模板schema带OKF默认值")
    init_repo = base / "init_repo"
    init_repo.mkdir()
    r = json.loads(handle_init_wiki({"repo_path": str(init_repo)}))
    check("init_wiki", "初始化成功", "error" not in r, str(r)[:200])
    new_schema = init_repo / "repowiki" / "schema.yaml"
    check("init_wiki", "生成schema.yaml", new_schema.exists(), str(new_schema))
    if new_schema.exists():
        st = new_schema.read_text(encoding="utf-8")
        check("init_wiki", "模板含okf_version", 'okf_version: "0.2"' in st, "")
        check("init_wiki", "模板含default_stale_days", "default_stale_days: 90" in st, "")

    # ================================================================
    print("\n[12] get_prompt — OKF v0.2 规范段")
    r = json.loads(handle_get_prompt({"prompt_type": "system_leaf", "session_id": sid}, store))
    prompt_text = r.get("content", "") or json.dumps(r, ensure_ascii=False)
    check(
        "get_prompt",
        "含OKF v0.2合规段",
        "OKF (Open Knowledge Format) v0.2" in prompt_text,
        prompt_text[:200],
    )
    check("get_prompt", "含actor约定", "human:<id>" in prompt_text, "")
    check("get_prompt", "含status词汇表", "draft | stable | deprecated" in prompt_text, "")
    check("get_prompt", "含stale_after说明", "stale_after" in prompt_text, "")

    # output_dir-only call (no session/repo_path): the most direct locator
    r = json.loads(
        handle_get_prompt({"prompt_type": "system_leaf", "output_dir": str(output_dir)}, store)
    )
    prompt_text2 = r.get("content", "") or json.dumps(r, ensure_ascii=False)
    check(
        "get_prompt",
        "仅output_dir也注入OKF段",
        "OKF (Open Knowledge Format) v0.2" in prompt_text2,
        prompt_text2[:200],
    )

    # ================================================================
    print("\n[13] index/log — §8/§9 格式")
    idx = output_dir / "wiki" / "index.md"
    check("index", "index.md存在", idx.exists(), "")
    if idx.exists():
        it = idx.read_text(encoding="utf-8")
        check(
            "index", "frontmatter含okf_version", "okf_version" in read_fm(idx), read_fm(idx)[:150]
        )
        check("index", "§8 bullet格式", "* [" in it, it[:300])
    # team-layout Phase 1 (D5): 操作日志改为月度分片 log-YYYY-MM.md（纯追加），
    # 旧版单文件 log.md 不再产生——两者取其一做 §9 格式校验
    wiki_dir = output_dir / "wiki"
    log = wiki_dir / "log.md"
    shards = sorted(wiki_dir.glob("log-*.md")) if wiki_dir.is_dir() else []
    if log.exists() or shards:
        lt = (log if log.exists() else shards[-1]).read_text(encoding="utf-8")
        check("log", "§9日期分组", "## " in lt and "* **" in lt, lt[:300])
    else:
        check("log", "log.md存在", False, "log.md not found")

    # ================================================================
    print("\n[14] schema_generator — 默认conventions")
    from codewiki.mcp.tools.schema_generator import generate_schema

    gen_dir = base / "gen_schema"
    gen_dir.mkdir()
    schema = generate_schema("demo", {}, ["python"], gen_dir, ["core", "utils"])
    conv = schema.get("conventions", {})
    check(
        "schema_generator", "okf_version默认0.2", conv.get("okf_version") == "0.2", str(conv)[:200]
    )
    check(
        "schema_generator",
        "default_stale_days默认90",
        conv.get("default_stale_days") == 90,
        str(conv)[:200],
    )

    # ================================================================
    print("\n[15] close_session — 收尾")
    r = json.loads(handle_close_session({"repo_path": str(fake_repo)}, store))
    check("close_session", "无错误返回", "error" not in r or r.get("status"), str(r)[:300])

    # ================================================================
    print(f"\n=== 结果: {_passed} 通过, {_failed} 失败 ===")
    if _failures:
        print("\n失败明细:")
        for f in _failures:
            print(" -", f[:400])
    shutil.rmtree(base, ignore_errors=True)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
