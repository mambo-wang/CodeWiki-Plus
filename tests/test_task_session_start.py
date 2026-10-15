"""Tests for the SessionStart task hook (codewiki/hooks/task_session_start.py).

The hook is exercised the same way CodeBuddy runs it: as a subprocess with the
event JSON on stdin, reading the ``{continue, hookSpecificOutput}`` JSON from
stdout. The repo root is forced via CODEBUDDY_PROJECT_DIR so the hook reads a
crafted tmp repo instead of the real one.

Covered:
  - backlog present  -> additionalContext carries the catch-up distillation
    instruction with per-task counts;
  - no backlog       -> no catch-up section (don't disturb);
  - corrupt index    -> silent degradation, still valid output;
  - missing index    -> frontmatter fallback still counts the backlog.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent.parent / "codewiki" / "hooks" / "task_session_start.py"

EVENT = json.dumps(
    {
        "session_id": "test-session",
        "cwd": "/",
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
)


def _run_hook(repo: Path, hook: Path = HOOK) -> dict:
    env = dict(os.environ)
    env["CODEBUDDY_PROJECT_DIR"] = str(repo)
    # Deterministic UTF-8 stdout regardless of the Windows console code page.
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=EVENT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, f"hook failed: {proc.stderr}"
    return json.loads(proc.stdout)


def _context(out: dict) -> str:
    assert out["continue"] is True
    return out["hookSpecificOutput"]["additionalContext"]


def _write_raw_index(repo: Path, entries: list) -> None:
    raw_dir = repo / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".index.json").write_text(
        json.dumps({"files": entries}, ensure_ascii=False), encoding="utf-8"
    )


def _write_raw_file(repo: Path, name: str, task_id: str, status: str = "pending") -> None:
    raw_dir = repo / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / name).write_text(
        f'---\nstatus: {status}\ntask_id: "{task_id}"\n---\n\nuser: hi', encoding="utf-8"
    )


def test_backlog_injects_catchup_instruction(tmp_path):
    # Two pending captures for task-one, one distilled (ignored), one unbound.
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    _write_raw_file(tmp_path, "conv-b.md", "task-one")
    _write_raw_file(tmp_path, "conv-c.md", "task-two", status="distilled")
    _write_raw_file(tmp_path, "conv-d.md", "")
    _write_raw_index(
        tmp_path,
        [
            {"relpath": "conv-a.md", "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-b.md", "status": "pending", "task_id": "task-one"},
            {"relpath": "conv-c.md", "status": "distilled", "task_id": "task-two"},
            {"relpath": "conv-d.md", "status": "pending", "task_id": ""},
            # Stale entry: file no longer exists — must not be counted.
            {"relpath": "conv-gone.md", "status": "pending", "task_id": "task-one"},
        ],
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" in ctx
    assert "3 条" in ctx  # 2 x task-one + 1 unbound
    assert "任务 task-one: 2 条" in ctx
    assert "未关联任务: 1 条" in ctx
    # Distillation is delegated to an async subagent, not run inline by the
    # main agent; the agent answers immediately and re-pulls context at the
    # next natural pause point.
    assert "蒸馏 worker" in ctx
    assert "distill-worker.md" in ctx
    assert "异步" in ctx
    assert "阻塞式" not in ctx
    assert "重新 get_task_context" in ctx
    assert 'distill_conversation(mode="prepare", task_id=<绑定的任务id>)' in ctx
    # ADR-0002: task memories are direct-written by distillation — only the
    # note draft gate remains in the injected instructions.
    assert "confirm_note" in ctx
    assert "confirm_task_memories" not in ctx


def test_no_backlog_no_catchup_section(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one", status="distilled")
    _write_raw_index(
        tmp_path,
        [
            {"relpath": "conv-a.md", "status": "distilled", "task_id": "task-one"},
        ],
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" not in ctx
    # Base task-binding guidance is still present.
    assert "ask_followup_question" in ctx


def test_corrupt_index_degrades_silently(tmp_path):
    raw_dir = tmp_path / "repowiki" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / ".index.json").write_text("{not valid json", encoding="utf-8")

    out = _run_hook(tmp_path)  # must not raise / must stay valid JSON
    ctx = _context(out)
    assert "【补蒸馏】" not in ctx
    assert "ask_followup_question" in ctx


def test_missing_index_falls_back_to_frontmatter(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    _write_raw_file(tmp_path, "conv-b.md", "task-one", status="distilled")
    # No .index.json at all.

    ctx = _context(_run_hook(tmp_path))
    assert "【补蒸馏】" in ctx
    assert "任务 task-one: 1 条" in ctx


def test_doctrine_injected_when_present(tmp_path):
    wiki = tmp_path / "repowiki" / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "doctrine.md").write_text(
        "---\ntype: Doctrine\nstatus: stable\n---\n\n## Operating Thesis\n\nWrite deep modules.\n",
        encoding="utf-8",
    )

    ctx = _context(_run_hook(tmp_path))
    assert "【项目定向】" in ctx
    assert "Write deep modules." in ctx
    # Frontmatter noise is stripped, doctrine rides on the same hard channel.
    assert "type: Doctrine" not in ctx


def test_doctrine_absent_no_section(tmp_path):
    ctx = _context(_run_hook(tmp_path))
    assert "【项目定向】" not in ctx


# ---------------------------------------------------------------------------
# P2-2 (claude-mem borrowing, thin): knowledge-base overview — the KB's
# existence and the cheapest retrieval entries surface before work starts.
# ---------------------------------------------------------------------------


def test_knowledge_overview_injected_when_notes_present(tmp_path):
    notes = tmp_path / "repowiki" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    for name in ("2026-08-01-old.md", "2026-08-20-newer.md", "2026-09-01-newest.md"):
        (notes / name).write_text("---\ntype: lesson\n---\nbody", encoding="utf-8")

    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" in ctx
    assert "3 条笔记" in ctx
    # newest-first: the newest filename rides along
    assert "2026-09-01-newest" in ctx
    # retrieval strategy pointers (P0-3's call-time channel, mirrored here)
    assert "by_file" in ctx
    assert "mode='check'" in ctx


def test_knowledge_overview_absent_when_no_notes(tmp_path):
    # repowiki exists but notes/ empty → no section (don't disturb)
    (tmp_path / "repowiki").mkdir(parents=True, exist_ok=True)
    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" not in ctx


def test_knowledge_overview_absent_when_no_repowiki(tmp_path):
    ctx = _context(_run_hook(tmp_path))
    assert "【知识库提示】" not in ctx


# ---------------------------------------------------------------------------
# 补蒸馏委托按宿主家族分支：claude 家族自定义子代理拿不到 MCP 权限（实测），
# 改委托内置 general-purpose 子代理；CodeBuddy 保留自定义「蒸馏 worker」。
# ---------------------------------------------------------------------------


def test_qoder_copy_delegates_to_general_purpose(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    hook = tmp_path / ".qoder" / "hooks" / "task_session_start.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)

    ctx = _context(_run_hook(tmp_path, hook=hook))
    assert "【补蒸馏】" in ctx
    assert "general-purpose" in ctx
    assert ".qoder/agents/distill-worker.md" in ctx  # host-aware playbook path
    assert "拿不到 MCP 权限" in ctx
    assert "「蒸馏 worker」subagent" not in ctx  # custom-agent wording must not leak


def test_active_tasks_listed_in_one_chooser_box(tmp_path):
    """用户反馈「任务关联经常弹多个框」：注入文案必须钉死单框 + 一框列全。

    ask_followup_question 的 schema 建议「2-4 个 options」，Agent 会照做把任务
    拆进多个 question 或分多次调用 —— 这是多框的根因。注入的硬约束必须显式
    覆盖该建议，并要求把全部 active 任务放进同一个 question 的 options。
    """
    tasks_dir = tmp_path / "repowiki" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / ".index.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {"id": "t1", "title": "任务一", "status": "active"},
                    {"id": "t2", "title": "任务二", "status": "active"},
                    {"id": "t3", "title": "已完成任务", "status": "completed"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ctx = _context(_run_hook(tmp_path))
    assert "只弹一次，一框列全" in ctx
    assert "1 次 ask_followup_question" in ctx
    assert "只放 1 个 question" in ctx
    assert "新建任务两步弹框" not in ctx  # 两步弹框是第二个框的来源，已废止为兜底

    # 全部 active 任务出现在同一个 options 清单里（已完成任务不出现）。
    options_block = ctx.split("该 question 的 options（按顺序）：")[1].split("【结果判定】")[0]
    assert "    - 任务一（task_id=t1）" in options_block
    assert "    - 任务二（task_id=t2）" in options_block
    assert "已完成任务" not in options_block
    assert "新建任务…（在输入框直接输入名称）" in options_block
    assert "跳过" in options_block


def test_codebuddy_copy_keeps_worker_delegation(tmp_path):
    _write_raw_file(tmp_path, "conv-a.md", "task-one")
    hook = tmp_path / ".codebuddy" / "hooks" / "task_session_start.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)

    ctx = _context(_run_hook(tmp_path, hook=hook))
    assert "【补蒸馏】" in ctx
    assert "「蒸馏 worker」subagent" in ctx
    assert ".codebuddy/agents/distill-worker.md" in ctx
    assert "general-purpose" not in ctx


# ---------------------------------------------------------------------------
# 弹框通道按宿主分档：Qoder 的 AskUserQuestion 单题 options 是硬上限 4（超了调用
# 直接失败），CodeBuddy 的 ask_followup_question 只是「建议 2-4」。写死前者会让
# Qoder 用户在任务数 >2 时一个框都弹不出来（2026-09-30 Qoder CN 实测定案）。
# ---------------------------------------------------------------------------

_LONG_TITLE = "统一知识存储层（KnowledgeStore 动词式门面）"


def _write_tasks_index(repo: Path, tasks: list) -> None:
    tasks_dir = repo / "repowiki" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / ".index.json").write_text(
        json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8"
    )


def _install_qoder_copy(tmp_path: Path) -> Path:
    hook = tmp_path / ".qoder" / "hooks" / "task_session_start.py"
    hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK, hook)
    return hook


def _five_active_tasks() -> list:
    tasks = [{"id": f"t{i}", "title": f"任务{i}", "status": "active"} for i in range(1, 6)]
    tasks[0]["title"] = _LONG_TITLE
    return tasks


def test_qoder_copy_uses_capped_chooser_and_lists_rest_in_body(tmp_path):
    _write_tasks_index(tmp_path, _five_active_tasks())

    ctx = _context(_run_hook(tmp_path, hook=_install_qoder_copy(tmp_path)))
    assert "AskUserQuestion" in ctx
    assert "ask_followup_question" not in ctx  # 宿主没有这个工具，照做必然调用失败
    assert "硬上限 4 个" in ctx
    assert "拆成多个 question" in ctx

    options_block = ctx.split("该 question 的 options（按顺序）：")[1].split("正文任务清单")[0]
    # 3 个任务 + 跳过 = 恰好 4 个 options
    assert options_block.count("label=") == 4
    assert "label=「跳过」" in options_block
    assert "任务4" not in options_block and "任务5" not in options_block

    # 长中文标题截断成短 label，完整标题与 task_id 留在 description
    assert f"label=「{_LONG_TITLE[:12]}」" in options_block
    assert f"description=「{_LONG_TITLE}」（task_id=t1）" in options_block

    # 未进选项的任务仍然可见（正文清单），由「其他」自由输入承接
    # 「正文任务清单」在硬约束段落里也被提到一次，取最后一次出现的那段
    body_block = ctx.rsplit("正文任务清单", 1)[1].split("【结果判定】")[0]
    assert "任务4（task_id=t4）" in body_block
    assert "任务5（task_id=t5）" in body_block
    assert "选「其他」" in ctx


def test_qoder_copy_options_are_the_most_recent_tasks(tmp_path):
    # t4/t5 最近在推进（memories 最新），created 最早也不该被挤掉。
    _write_tasks_index(tmp_path, _five_active_tasks())
    tasks_dir = tmp_path / "repowiki" / "tasks"
    for tid in ("t1", "t2", "t3", "t4", "t5"):
        d = tasks_dir / tid / "memories"
        d.mkdir(parents=True, exist_ok=True)
        m = d / "u.md"
        m.write_text("x", encoding="utf-8")
        os.utime(m, (1_700_000_000, 1_700_000_000))
    for tid, ts in (("t4", 1_800_000_000), ("t5", 1_900_000_000)):
        m = tasks_dir / tid / "memories" / "u.md"
        os.utime(m, (ts, ts))

    ctx = _context(_run_hook(tmp_path, hook=_install_qoder_copy(tmp_path)))
    options_block = ctx.split("该 question 的 options（按顺序）：")[1].split("正文任务清单")[0]
    assert "任务5" in options_block and "任务4" in options_block
    # t1..t3 里最近的一条补位，其余进正文清单
    assert "任务3" not in options_block and "任务2" not in options_block


def _options_block(ctx: str) -> str:
    """截出「该 question 的 options（按顺序）：」之后的选项段。"""
    return ctx.split("该 question 的 options（按顺序）：")[1].split("【结果判定】")[0]


def _active_index(n: int) -> list:
    return [{"id": f"t{i}", "title": f"任务{i}", "status": "active"} for i in range(1, n + 1)]


def test_qoder_channel_option_count_stays_within_tool_bounds(tmp_path):
    """AskUserQuestion 的 options 是硬区间 2-4：0 个任务时只给「跳过」弹不出来。

    0 个进行中任务 = 新仓库/新克隆的首个会话，正是最该引导建任务的一次，不能
    让选项数越界把整条任务关联流程废掉。
    """
    for n in (0, 1, 2, 3, 4, 9):
        repo = tmp_path / f"r{n}"
        if n:
            _write_tasks_index(repo, _active_index(n))
        ctx = _context(_run_hook(repo, hook=_install_qoder_copy(repo)))
        labels = re.findall(r"label=「([^」]+)」", _options_block(ctx))
        assert 2 <= len(labels) <= 4, f"{n} 个任务 → {len(labels)} 个选项: {labels}"
        assert labels[-1] == "跳过"
        assert len(set(labels)) == len(labels)
        if n < 3:
            assert "新建任务" in labels  # 空位补「新建任务」，新建不只靠「其他」
        else:
            assert "新建任务" not in labels


def test_qoder_channel_no_dangling_body_list_when_all_tasks_fit(tmp_path):
    # 任务全进了选项 → 不该再指着一份并不存在的「正文任务清单」下指令
    _write_tasks_index(tmp_path, _active_index(2))

    ctx = _context(_run_hook(tmp_path, hook=_install_qoder_copy(tmp_path)))
    assert "进行中共" not in ctx
    assert "正文任务清单" not in ctx


def test_qoder_channel_labels_stay_distinct_on_shared_prefix(tmp_path):
    # 长中文标题前 12 字相同（task_id 由标题生成，换 id 也一样撞），重复 label
    # 会让用户在弹框里分不清选项，故撞车时按前缀逐步延长。
    _write_tasks_index(
        tmp_path,
        [
            {
                "id": f"k{i}",
                "title": f"统一知识存储层（KnowledgeStore 变体{i} 门面）",
                "status": "active",
            }
            for i in (1, 2, 3)
        ],
    )

    ctx = _context(_run_hook(tmp_path, hook=_install_qoder_copy(tmp_path)))
    labels = re.findall(r"label=「([^」]+)」", _options_block(ctx))
    assert len(labels) == 4 and len(set(labels)) == 4


def test_unlimited_channel_still_lists_every_task(tmp_path):
    """CodeBuddy 档不受本次改动影响：仍然一框列全 5 个任务。"""
    _write_tasks_index(tmp_path, _five_active_tasks())

    ctx = _context(_run_hook(tmp_path))  # 包内源副本 = 无限选项档
    assert "ask_followup_question" in ctx
    assert "AskUserQuestion" not in ctx
    options_block = ctx.split("该 question 的 options（按顺序）：")[1].split("【结果判定】")[0]
    for i in range(1, 6):
        assert f"（task_id=t{i}）" in options_block


# ---------------------------------------------------------------------------
# 任务索引缺失/损坏时的回退：.index.json 是 gitignored 的本机可重建缓存，
# 刚克隆或刚换机器的仓库往往没有它——不回退就弹不出已有任务。
# ---------------------------------------------------------------------------


def _write_task_md(repo: Path, task_id: str, title: str, status: str) -> None:
    d = repo / "repowiki" / "tasks" / task_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text(
        f"---\ntype: task\ntask_id: {task_id}\ntitle: {title}\nstatus: {status}\n---\n\n正文\n",
        encoding="utf-8",
    )


def test_active_tasks_fallback_scan_when_index_absent(tmp_path):
    _write_task_md(tmp_path, "keep", "回退任务", "active")
    _write_task_md(tmp_path, "drop", "已完成任务", "completed")
    # 故意不写 .index.json

    ctx = _context(_run_hook(tmp_path))
    assert "回退任务（task_id=keep）" in ctx
    assert "已完成任务" not in ctx


def test_active_tasks_fallback_scan_when_index_corrupt(tmp_path):
    _write_task_md(tmp_path, "keep", "损坏索引仍可见", "active")
    tasks_dir = tmp_path / "repowiki" / "tasks"
    (tasks_dir / ".index.json").write_text("{not valid json", encoding="utf-8")

    ctx = _context(_run_hook(tmp_path))
    assert "损坏索引仍可见（task_id=keep）" in ctx


def test_empty_index_also_falls_back_to_scan(tmp_path):
    # 索引存在但 tasks 为空（新克隆后被清空的缓存）——同样要回退到目录扫描
    _write_task_md(tmp_path, "keep", "空索引用目录扫描", "active")
    _write_tasks_index(tmp_path, [])

    ctx = _context(_run_hook(tmp_path))
    assert "空索引用目录扫描（task_id=keep）" in ctx
