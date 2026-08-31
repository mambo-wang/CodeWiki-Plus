"""Boundary tests for the unified KnowledgeStore (RFC docs/plans/knowledge-store-rfc.md).

The store is the single persistence layer the migrated MCP handlers delegate to.
These tests exercise it directly at its boundary — no MCP session or tool
dispatch — so they pin the invariants the handlers rely on:

  - raw capture: frontmatter round-trip, content-hash dedup, session supersede,
    task_id inheritance, one-shot binding consumption;
  - task index self-heal (directory is truth, .index.json is a cache);
  - locked per-user memory append (ghost task → 0);
  - surgical frontmatter update preserving unknown keys;
  - delete cascade (directory + index entry + bindings);
  - raw-index sync after distillation (removed vs kept).
"""

from __future__ import annotations

from pathlib import Path

from codewiki.src.frontmatter import (
    format_frontmatter_value,
    inject_okf_frontmatter,
    parse_frontmatter,
)
from codewiki.src.store import KnowledgeStore, slugify

_TURNS = [{"role": "user", "content": "如何部署?"}, {"role": "assistant", "content": "用 docker."}]


def _store(tmp_path: Path) -> KnowledgeStore:
    return KnowledgeStore(tmp_path / "repowiki")


def test_capture_round_trip_and_index(tmp_path):
    store = _store(tmp_path)
    r = store.capture_raw(_TURNS, source_session_id="s1", task_id="task-a")
    assert r["kind"] == "captured"
    assert r["task_id"] == "task-a"
    # Frontmatter is parseable and carries the capture metadata.
    raw = store.raw_dir / r["relpath"].split("/", 1)[1]
    fm, body = parse_frontmatter(raw.read_text(encoding="utf-8"))
    assert fm["status"] == "pending"
    assert fm["task_id"] == "task-a"
    assert fm["content_hash"] == r["content_hash"]
    assert "user: 如何部署?" in body


def test_dedup_and_attribution_split(tmp_path):
    store = _store(tmp_path)
    r1 = store.capture_raw(_TURNS, source_session_id="s1", task_id="task-a")
    # Same content + same task → duplicate.
    assert (
        store.capture_raw(_TURNS, source_session_id="s2", task_id="task-a")["kind"] == "duplicate"
    )
    # Same content + different attribution → distinct capture (task_id in hash).
    r2 = store.capture_raw(_TURNS, source_session_id="s2", task_id="task-b")
    assert r2["kind"] == "captured" and r2["relpath"] != r1["relpath"]


def test_supersede_inherits_task_id_and_consumes_binding(tmp_path):
    store = _store(tmp_path)
    store.write_binding("sess", "task-a")
    r1 = store.capture_raw(_TURNS, source_session_id="sess")
    assert r1["kind"] == "captured" and r1["task_id"] == "task-a"
    assert r1["consumed_binding"] and not store.read_binding("sess")

    longer = _TURNS + [{"role": "user", "content": "还有呢?"}]
    r2 = store.capture_raw(longer, source_session_id="sess")
    assert r2["kind"] == "superseded" and r2["relpath"] == r1["relpath"]
    # Binding is gone; attribution survives via the superseded entry.
    assert r2["task_id"] == "task-a" and r2["task_source"] == "binding-inherited"


def test_task_index_self_heals_from_directory(tmp_path):
    store = _store(tmp_path)
    task = {
        "id": "task-a",
        "title": "任务A",
        "status": "active",
        "created_at": "2026-08-31T00:00:00+00:00",
    }
    store.write_task_file(task, "描述")
    # No index file was written by write_task_file alone; read_task_index
    # rebuilds from the directory scan.
    idx = store.read_task_index()
    assert [t["id"] for t in idx] == ["task-a"]
    assert store.find_task("task-a")["title"] == "任务A"
    assert store.task_description("task-a") == "描述"


def test_append_memories_locked_and_ghost_task(tmp_path):
    store = _store(tmp_path)
    store.write_task_file(
        {"id": "t1", "title": "T", "status": "active", "created_at": "2026-01-01T00:00:00+00:00"},
        "",
    )
    assert store.append_memories("t1", ["第一条", "第二条"], user="u1") == 2
    own, legacy, others = store.collect_memory_files("t1", "u1")
    raw, summary, entries, _bytes = store.parse_memory_file(own)
    assert len(entries) == 2 and all(e.startswith("### ") for e in entries)
    assert summary == "" and not legacy.exists() and others == []

    # Ghost task (deleted) → no write, no raise.
    assert store.append_memories("no-such-task", ["x"], user="u1") == 0


def test_update_frontmatter_preserves_unknown_keys(tmp_path):
    store = _store(tmp_path)
    store.write(
        "notes/n.md",
        '---\ntype: note\ntitle: "旧"\nstatus: draft\ncustom_key: keep\n---\n\nbody',
    )
    assert store.update_frontmatter("notes/n.md", status="confirmed", title="新")
    text = (store.root / "notes" / "n.md").read_text(encoding="utf-8")
    assert "custom_key: keep" in text
    assert "status: confirmed" in text
    assert "title: 新" in text


def test_delete_task_cascades(tmp_path):
    store = _store(tmp_path)
    store.write_task_file(
        {"id": "t1", "title": "T", "status": "active", "created_at": "2026-01-01T00:00:00+00:00"},
        "",
    )
    store.write_binding("sess-9", "t1")
    assert store.delete_task("t1") == 1
    assert not (store.tasks_dir / "t1").exists()
    assert store.find_task("t1") is None
    assert not store.read_binding("sess-9")


def test_sync_raw_index_removed_vs_kept(tmp_path):
    store = _store(tmp_path)
    r = store.capture_raw(_TURNS, source_session_id="s1")
    assert len(store.pending_raws_by_task().get("", [])) == 1

    # Kept (keep_raw): flip index status, file stays pending-free.
    store.sync_raw_index(r["relpath"], removed=False)
    assert store.pending_raws_by_task() == {}

    # Removed: the file already left raw/ (deleted/archived by the distill
    # flow) — sync_raw_index only drops the index entry.
    r2 = store.capture_raw(_TURNS, source_session_id="s2", task_id="t")
    (store.raw_dir / r2["relpath"].split("/", 1)[1]).unlink()
    store.sync_raw_index(r2["relpath"], removed=True)
    assert store.pending_raws_by_task() == {}


def test_frontmatter_round_trip_block_lists(tmp_path):
    doc = inject_okf_frontmatter(
        "# T\n\nbody",
        type_="note",
        title='带 "引号"',
        status="draft",
        okf_tags=["a", "b"],
        metadata_extra={"task_id": "产品维护", "n": 3},
    )
    fm, body = parse_frontmatter(doc)
    assert fm["title"] == '带 "引号"'
    assert fm["tags"] == ["a", "b"]
    assert fm["metadata"]["task_id"] == "产品维护"
    assert fm["metadata"]["n"] == 3
    assert body.strip() == "# T\n\nbody"


def test_slugify(tmp_path):
    assert slugify("统一知识存储层（KnowledgeStore）")
    assert slugify("a/b:c") == "a-b-c"
    assert slugify("   ") == ""


def test_format_value_quotes_yaml_reserved_words():
    # Legacy readers (knowledge_loop / note_consolidation / doctrine) parse
    # frontmatter with yaml.safe_load (PyYAML = YAML 1.1): a bare "on" /
    # "Yes" would come back as a boolean. Reserved literals stay quoted.
    import yaml

    for word in ("on", "Off", "YES", "no", "n", "true", "null"):
        rendered = format_frontmatter_value(word)
        assert yaml.safe_load(f"k: {rendered}")["k"] == word
        fm, _ = parse_frontmatter(f"---\nk: {rendered}\n---\nx")
        assert fm["k"] == word
    # Plain unambiguous strings stay unquoted (corpus convention).
    assert format_frontmatter_value("confirmed") == "confirmed"


def test_update_frontmatter_metadata_routing(tmp_path):
    from codewiki.src.store import KnowledgeStore

    store = KnowledgeStore(tmp_path / "repowiki")

    # Into an EXISTING metadata block.
    store.write("notes/a.md", "---\ntype: note\nmetadata:\n  old: 1\nstatus: draft\n---\n\nbody")
    store.update_frontmatter("notes/a.md", **{"metadata.new": "added"})
    text = (store.root / "notes/a.md").read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)
    assert fm["metadata"] == {"old": 1, "new": "added"}
    assert "metadata.new:" not in text  # never a literal top-level key

    # Creating a metadata block when the file has none.
    store.write("notes/b.md", "---\ntype: note\nstatus: draft\n---\n\nbody")
    store.update_frontmatter("notes/b.md", status="confirmed", **{"metadata.task_id": "t1"})
    fm, _ = parse_frontmatter((store.root / "notes/b.md").read_text(encoding="utf-8"))
    assert fm["metadata"] == {"task_id": "t1"} and fm["status"] == "confirmed"

    # File without any frontmatter gains a well-formed fence.
    store.write("notes/c.md", "plain body")
    store.update_frontmatter("notes/c.md", status="draft", **{"metadata.k": "v"})
    fm, body = parse_frontmatter((store.root / "notes/c.md").read_text(encoding="utf-8"))
    assert fm["status"] == "draft" and fm["metadata"] == {"k": "v"}
    assert body.strip() == "plain body"


def test_atomic_write_thread_safe(tmp_path):
    import threading

    from codewiki.src.store import atomic_write

    target = tmp_path / "race.md"
    errors = []

    def writer(i):
        try:
            for j in range(25):
                atomic_write(target, f"content-{i}-{j}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert target.read_text(encoding="utf-8").startswith("content-")
