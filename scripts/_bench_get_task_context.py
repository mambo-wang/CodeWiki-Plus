"""临时性能基准：定位 get_task_context 慢的瓶颈。跑完即删。"""
import json
import pathlib
import time

from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools import task_manager as tm
from codewiki.mcp.tools.capture_conversation import pending_raws_by_task
from codewiki.mcp.tools import aggregation_state as agg

output_dir = pathlib.Path("d:/repos/CodeWiki-CN/repowiki")
task_id = "产品维护"


def bench(label, fn):
    t0 = time.perf_counter()
    r = fn()
    t1 = time.perf_counter()
    print(f"{label}: {(t1 - t0) * 1000:.1f}ms")
    return r


# 1. index
tasks = bench("_read_index", lambda: tm._read_index(output_dir))
task = tm._find_by_id(tasks, task_id)
print("task found:", task is not None)

# 2. task file
def _read_task_file():
    p = tm._task_path(output_dir, task_id)
    text = p.read_text(encoding="utf-8")
    m = tm.re.match(r"\A---\s*\n.*?\n---\s*\n?(.*)", text, tm.re.DOTALL)
    return m.group(1) if m else text

bench("task file read + regex", _read_task_file)

# 3. memories
def _mem():
    return tm._load_memories_layered(output_dir, task_id, 20, True)

mems = bench("_load_memories_layered", _mem)

# 4. notes full scan
def _notes_scan():
    found = []
    notes_dir = output_dir / "notes"
    for nf in sorted(notes_dir.glob("*.md")):
        try:
            text = nf.read_text(encoding="utf-8")
        except OSError:
            continue
        if tm._extract_fm(text, "task_id") != task_id:
            continue
        title = tm._extract_fm(text, "title") or nf.stem
        status = tm._extract_fm(text, "status") or "stable"
        found.append({"relpath": nf.name, "title": title, "status": status})
    return found

notes = bench("notes full scan (103 files)", _notes_scan)
print("  matched notes:", len(notes))

# 5. pending raw
bench("pending_raws_by_task", lambda: pending_raws_by_task(output_dir))

# 6. aggregation
bench("aggregation_summary", lambda: agg.aggregation_summary(output_dir))

# 7. FULL handler (第二遍，避免 import 冷启动影响)
store = SessionStore()
res = bench(
    "FULL handle_get_task_context",
    lambda: json.loads(tm.handle_get_task_context({"task_id": task_id, "output_dir": str(output_dir)}, store)),
)
print("keys:", list(res.keys()))

# 8. 分解：只扫 notes 一遍的纯耗时（放大 5 遍看稳定性）
def _scan_repeat():
    for _ in range(5):
        _notes_scan()

bench("notes scan x5 (稳定性)", _scan_repeat)
