"""Task-memory recall (search_task_memories) + auto-compaction driver.

Design: docs/任务记忆检索与自动压缩设计.md — entry-level BM25 recall over
one task's memories (in-memory, always fresh, never coupled to the wiki
corpus), and get_task_context dispatching compaction to an async worker
subagent via a payload-free compaction_action directive (no user gate;
ADR-0002 extension).
"""

from __future__ import annotations

import json

from codewiki.mcp.tools import task_manager as tm
from codewiki.src.store import KnowledgeStore


def _store():
    from codewiki.mcp.session import SessionStore

    return SessionStore()


def _call(fn, **kwargs) -> dict:
    return json.loads(fn(kwargs, _store()))


def _mk_task(tmp_path, title="调研任务") -> str:
    r = _call(tm.handle_create_task, repo_path=str(tmp_path), title=title)
    assert r["ok"] is True
    return r["task"]["id"]


def _append(output_dir, task_id, contents, user=None, **kw):
    ks = KnowledgeStore(output_dir)
    if user is None:
        from codewiki.src.config import user_id

        user = user_id(output_dir)
    return ks.append_memories(task_id, contents, user=user, **kw)


# --------------------------------------------------------------------------- #
# search_task_memories
# --------------------------------------------------------------------------- #


def test_old_entry_beyond_tail_window_is_recallable(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    # 30 entries; only the FIRST ones mention the distinctive keyword.
    _append(
        od,
        task_id,
        [f"常规进度记录 {i}：继续推进模块设计。" for i in range(28)]
        + [
            "早期结论：分布式锁选型 redlock 方案，理由是读写比例 10:1。",
            "早期结论：缓存层选 sqlite 而非 lmdb。",
        ],
    )
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="redlock 分布式锁 选型",
    )
    assert r["ok"] is True
    assert r["total_matched"] >= 1
    top = r["results"][0]
    assert "redlock" in top["snippet"]
    assert top["date"]  # timestamped entry, not a summary pseudo-entry
    assert top["est_tokens"] > 0
    assert r["corpus"]["entries"] >= 30


def test_compacted_archive_entry_recallable_with_flag(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    # The critical lesson sits among the OLDEST entries (outside the keep
    # window) so compaction actually moves it into the archive.
    _append(
        od,
        task_id,
        ["关键教训：Windows 下 sidecar 锁释放即删会撞 delete-pending，必须收进临界区。"]
        + [f"填充条目 {i}：日常推进。" for i in range(44)],
    )
    # Compact: prepare (agent writes the summary), submit.
    r = _call(tm.handle_compact_task_memories, repo_path=str(tmp_path), task_id=task_id)
    assert r["compaction_needed"] is True
    r = _call(
        tm.handle_compact_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        mode="submit",
        summary="早期条目：日常推进记录。关键教训：Windows 锁释放时序。",
    )
    assert r["ok"] is True and r["compressed"] >= 1

    # The critical lesson is now compacted away from the hot layer…
    ctx = _call(tm.handle_get_task_context, repo_path=str(tmp_path), task_id=task_id)
    assert "sidecar 锁释放即删" not in ctx["memories"]

    # …but searchable from the archive.
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="sidecar 锁 delete-pending 临界区",
    )
    assert r["ok"] is True
    hits = [x for x in r["results"] if "sidecar" in x["snippet"]]
    assert hits, "compacted entry must be recallable from the archive"
    assert hits[0]["archived"] is True
    assert hits[0]["file"].startswith("tasks/") and "memories-archive/" in hits[0]["file"]
    assert r["corpus"]["archived_entries"] >= 1
    assert "hint" in r  # archive-hit guidance

    # include_archive=false drops it.
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="sidecar delete-pending",
        include_archive=False,
    )
    assert not [x for x in r["results"] if x.get("archived")]


def test_privacy_others_excluded_by_default(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    _append(od, task_id, ["本人条目：我负责检索层设计。"])
    _append(od, task_id, ["同事条目：他的调研细节关于量化交易策略。"], user="teammate-a")

    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="量化交易 策略",
    )
    assert r["ok"] is True
    assert r["results"] == []  # search is never broader than reading

    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="量化交易 策略",
        include_others=True,
    )
    assert any("量化交易" in x["snippet"] for x in r["results"])
    assert all(x["owner"] == "teammate-a" for x in r["results"] if "量化" in x["snippet"])


def test_summary_pseudo_entry_searchable(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    # 45 entries → beyond the 40-entry threshold, so compaction runs.
    _append(od, task_id, [f"条目 {i}" for i in range(45)])
    _call(
        tm.handle_compact_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        mode="submit",
        summary="早期记忆摘要：完成了调研阶段并确定了向量库选型 milvus。",
    )
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="milvus 向量库 选型",
    )
    kinds = [x["kind"] for x in r["results"]]
    assert "summary" in kinds  # the compaction summary itself is recallable


def test_input_validation_and_ghost_task(tmp_path):
    _mk_task(tmp_path)
    assert "error" in _call(
        tm.handle_search_task_memories, repo_path=str(tmp_path), task_id="", query="x"
    )
    assert "error" in _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id="不存在的任务",
        query="x",
    )
    assert "error" in _call(
        tm.handle_search_task_memories, repo_path=str(tmp_path), task_id="调研任务", query=""
    )


def test_legacy_only_task_searchable(tmp_path):
    """Pre-split tasks (e.g. 产品维护) keep everything in memories.md."""
    task_id = _mk_task(tmp_path)
    legacy = tmp_path / "repowiki" / "tasks" / task_id / "memories.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        "### 2026-08-01 09:00\n\n早期教训：老模块的迁移脚本要幂等，否则重跑翻倍。\n\n"
        "### 2026-08-20 15:30\n\n后续：迁移完成。\n",
        encoding="utf-8",
    )
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="迁移 脚本 幂等",
    )
    assert r["ok"] is True
    hits = [x for x in r["results"] if "幂等" in x["snippet"]]
    assert hits, "legacy-file entry must be recallable"
    assert hits[0]["owner"] == "legacy"
    assert hits[0]["file"].endswith("memories.md")


def test_others_archive_needs_both_flags(tmp_path):
    """include_others + include_archive together surface a teammate's archive."""
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    _append(od, task_id, [f"本人条目 {i}" for i in range(3)])
    # Teammate with a live file and a compacted archive.
    mate_live = od / "tasks" / task_id / "memories" / "teammate-b.md"
    mate_live.parent.mkdir(parents=True, exist_ok=True)
    mate_live.write_text(
        "## 早期记忆（摘要）\n\n同事早期工作的摘要段。\n\n### 2026-09-01 10:00\n\n最近条目。\n",
        encoding="utf-8",
    )
    mate_arc = od / "tasks" / task_id / "memories-archive" / "teammate-b.md"
    mate_arc.parent.mkdir(parents=True, exist_ok=True)
    mate_arc.write_text(
        "### 2026-08-01 10:00\n\n同事的旧结论：消息队列选 rocketmq，理由是顺序消息。\n",
        encoding="utf-8",
    )
    # Default: nothing from teammate-b (live nor archive).
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="rocketmq 顺序消息",
    )
    assert not any("rocketmq" in x["snippet"] for x in r["results"])
    # include_others + default include_archive: the archived conclusion surfaces.
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="rocketmq 顺序消息",
        include_others=True,
    )
    hits = [x for x in r["results"] if "rocketmq" in x["snippet"]]
    assert hits, "teammate archive must surface with include_others (+default archive)"
    assert hits[0]["archived"] is True
    assert hits[0]["owner"] == "teammate-b"
    # include_others + include_archive=False: archive dropped.
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="rocketmq 顺序消息",
        include_others=True,
        include_archive=False,
    )
    assert not any(x.get("archived") for x in r["results"])


def test_max_results_bounds(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    _append(od, task_id, [f"部署记录 {i}：k8s 滚动发布流程验证。" for i in range(10)])
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="k8s 滚动发布",
        max_results=3,
    )
    assert len(r["results"]) == 3
    assert r["total_matched"] >= 10  # total reflects the full match set
    # Overshoot clamps at 20; invalid input falls back to default.
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="k8s 滚动发布",
        max_results=99,
    )
    assert len(r["results"]) <= 20
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="k8s 滚动发布",
        max_results="not-a-number",
    )
    assert "results" in r  # graceful fallback, not an unhandled crash


def test_always_fresh_after_append(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    _append(od, task_id, ["初始条目。"])
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="新写入的结论",
    )
    assert r["results"] == []
    _append(od, task_id, ["新写入的结论：检索通道走内存评分。"])
    r = _call(
        tm.handle_search_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        query="新写入的结论",
    )
    assert any("内存评分" in x["snippet"] for x in r["results"])


# --------------------------------------------------------------------------- #
# Auto-compaction driver (compaction_action in get_task_context)
# --------------------------------------------------------------------------- #


def test_get_task_context_carries_compaction_action(tmp_path):
    task_id = _mk_task(tmp_path)
    od = tmp_path / "repowiki"
    _append(od, task_id, [f"条目 {i}：推进事项。" for i in range(45)])

    ctx = _call(tm.handle_get_task_context, repo_path=str(tmp_path), task_id=task_id)
    assert ctx["compaction_due"] is True
    action = ctx["compaction_action"]
    assert action["task_id"] == task_id
    assert action["keep_recent"] == 20
    assert action["summary_max_chars"] == 4096
    # 派发指令，不是载荷：待压条目正文不得进主 Agent 上下文（压缩要省的字节
    # 不该先被注入一遍，且大段正文正是诱发「是否压缩」确认框的原因）。
    assert "entries_to_compress" not in action
    assert "条目 0：" not in json.dumps(ctx, ensure_ascii=False)
    assert "Task 工具" in action["dispatch"] and "异步" in action["dispatch"]
    assert 'mode="prepare"' in action["dispatch"] and 'mode="submit"' in action["dispatch"]
    assert task_id in action["dispatch"]
    # 子代理是全新上下文、没有会话，repo_path 必须写进配方，否则 prepare/submit
    # 一律撞上 "repo_path is required"，免确认压缩的主路径根本跑不通。
    assert action["repo_path"] == str(tmp_path)
    assert 'repo_path="' in action["dispatch"]
    assert 'mode="prepare", repo_path=' in action["dispatch"]
    assert 'mode="submit", repo_path=' in action["dispatch"]
    assert "无需向用户确认" in action["gate"]

    # After a submit, the work is done and the directive disappears.
    _call(
        tm.handle_compact_task_memories,
        repo_path=str(tmp_path),
        task_id=task_id,
        mode="submit",
        summary="早期 25 条为日常推进记录，无待办。",
    )
    ctx = _call(tm.handle_get_task_context, repo_path=str(tmp_path), task_id=task_id)
    assert ctx["compaction_due"] is False
    assert "compaction_action" not in ctx


def test_get_task_context_no_compaction_action_when_not_due(tmp_path):
    task_id = _mk_task(tmp_path)
    _append(tmp_path / "repowiki", task_id, ["一两条条目而已。"])
    ctx = _call(tm.handle_get_task_context, repo_path=str(tmp_path), task_id=task_id)
    assert ctx["compaction_due"] is False
    assert "compaction_action" not in ctx
