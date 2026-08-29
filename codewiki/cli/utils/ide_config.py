"""
IDE wiring utilities for CodeWiki hooks/subagents.

将任务记忆 hook/subagent 接线从「仅支持 CodeBuddy」扩展为支持市面上常见的
智能体（Qoder、Claude Code）。用户触发创建/启用 hook 时，自动检测项目根目录
存在哪些智能体配置目录（.codebuddy/.qoder/.claude/.gemini），检测到哪些就为哪些生成
对应 hook 注册与 subagent 定义。

核心设计：IDE 注册表（IDE_SPECS）驱动。IDE 差异（配置目录、settings.json、
agents 子目录、是否拷贝 distill-worker）收敛为数据表，新增一个 IDE 只需加一行。

本模块供 codewiki install-hooks CLI 命令与 MCP prompt 指引共用。
"""

import ast
import copy
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from codewiki.cli.utils.errors import FileSystemError
from codewiki.cli.utils.fs import safe_write
from codewiki.mcp.prompts import (
    _QWENWORK_CAPTURE_END,
    _QWENWORK_CAPTURE_SECTION,
    _QWENWORK_CAPTURE_START,
    _TASK_MEMORY_AGENTS_END,
    _TASK_MEMORY_AGENTS_SECTION,
    _TASK_MEMORY_AGENTS_START,
)

# ---------------------------------------------------------------------------
# IDE 注册表（核心契约）
# ---------------------------------------------------------------------------
# 每个 IDE 的配置目录、settings.json 文件名、agents 子目录、是否拷贝 distill-worker。
# 新增一个 IDE 只需在此加一行，CLI 命令与 prompt 自动获得支持。
#
# 两种接线模式：
#   - wiring: "hook"（默认）：IDE 支持 shell hook 事件（SessionStart/SessionEnd
#     携带 transcript_path 经 stdin 调脚本）——拷脚本、写 settings.json、拷 agent。
#   - wiring: "prompt"：宿主无 shell hook 机制，靠上下文注入 + Agent 中介执行
#     （如千问办公：AGENTS.md 自动加载等价 SessionStart；会话捕获由 Agent 按协议
#     调 MCP 工具完成）——只 upsert AGENTS.md 协议段，无 dir/settings/拷贝，
#     且不参与仓库目录自动检测（无仓库标记，仅显式 --ide 触发）。
#
# agent_file（可选）：subagent 定义源文件名。各宿主的 subagent frontmatter
# schema 不同——CodeBuddy 认 `tools: ReadFile` + `toolsMCP`，claude 家族
# （Qoder/Claude Code/Gemini CLI）认 `tools: Read, Write, mcp__<server>__<tool>`；
# 把 CodeBuddy 版喂给 claude 家族宿主会解析出空工具集、subagent 不可用。
# 缺省（如 codebuddy）拷贝 AGENT_FILE；安装后的目标文件名始终是 AGENT_FILE。
IDE_SPECS: dict[str, dict] = {
    "codebuddy": {
        "dir": ".codebuddy",
        "settings": "settings.json",
        "agents_dir": "agents",
        "copy_agent": True,
    },
    "qoder": {
        "dir": ".qoder",
        "settings": "settings.json",
        "agents_dir": "agents",
        "copy_agent": True,
        "agent_file": "distill-worker.claude.md",
    },
    "claude-code": {
        "dir": ".claude",
        "settings": "settings.json",
        "agents_dir": "agents",
        "copy_agent": True,
        "agent_file": "distill-worker.claude.md",
    },
    "gemini-cli": {
        "dir": ".gemini",
        "settings": "settings.json",
        "agents_dir": "agents",
        "copy_agent": True,
        "agent_file": "distill-worker.claude.md",
    },
    "qwenwork": {
        "wiring": "prompt",
        "dir": None,
    },
}

# 需要物理拷贝的 hook 脚本（IDE 不会自动创建，必须就位于目标项目）
HOOK_FILES = ("capture_session_end.py", "task_session_start.py")
# distill-worker subagent 定义文件（安装后的目标文件名；源变体见 IDE_SPECS.agent_file）
AGENT_FILE = "distill-worker.md"

# command 用项目相对路径（宿主以项目根为工作目录执行 hook 命令），不写机器
# 相关绝对路径——settings.json 随仓库共享，绝对路径提交后队友克隆到其他目录
# 即失效；各宿主的 $*_PROJECT_DIR 变量展开经实测不可靠，故不用占位符。
# 脚本本体经 __file__ 定位仓库，不依赖工作目录。
START_HOOK_CMD = 'python "{ide_dir}/hooks/task_session_start.py"'
END_HOOK_CMD = 'python "{ide_dir}/hooks/capture_session_end.py"'

# hook 事件注册骨架，command 运行时补全为相对路径命令
HOOKS_REGISTRATION = {
    "SessionStart": [
        {"matcher": "startup", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 15}]}
    ],
    "SessionEnd": [
        {"matcher": "other", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 30}]}
    ],
}


class IdeWiringError(RuntimeError):
    """Raised when IDE wiring fails."""


def _resolve_pkg_sources() -> Path:
    """定位 codewiki 包内源副本目录（hooks/ 与 agents/ 的父目录）。

    解析顺序：import codewiki 定位包目录 → CODEWIKI_HOME 环境变量指向的 checkout。
    均失败时抛出 IdeWiringError，附带 pip install 指引。
    """
    try:
        import codewiki

        return Path(os.path.dirname(codewiki.__file__))
    except ImportError:
        pass
    home = os.environ.get("CODEWIKI_HOME", "")
    if home:
        candidate = Path(home) / "codewiki"
        if candidate.is_dir():
            return candidate
    raise IdeWiringError(
        "Cannot locate the codewiki package source copies. "
        "Install it with `pip install codewiki`, or set the CODEWIKI_HOME "
        "environment variable to the checkout path."
    )


def detect_ide_dirs(repo: str) -> list[str]:
    """扫描项目根目录，返回已存在的 IDE 配置目录对应的 IDE 名称列表。

    存在 `.codebuddy/.qoder/.claude/.gemini` 中哪些目录就检测到哪些 IDE——
    即「用户用了哪些智能体就为哪些接线」。prompt 模式（千问办公）在仓库
    无标记目录，不参与自动检测，仅显式 ``--ide qwenwork`` 触发。
    """
    repo_path = Path(repo)
    return [
        name
        for name, spec in IDE_SPECS.items()
        if spec.get("dir") and (repo_path / spec["dir"]).is_dir()
    ]


def merge_settings_json(existing: Optional[dict], start_cmd: str, end_cmd: str) -> dict:
    """幂等合并 CodeWiki 的 hook 注册到现有 settings.json 配置。

    保留 existing 中全部既有键；对 hooks.SessionStart/SessionEnd 数组按 command
    去重后合并 CodeWiki 注册项，避免重复注册。历史旧格式条目（绝对路径、
    反斜杠路径或 ``$*_PROJECT_DIR`` 占位符形式）指向同一相对脚本路径时，
    原地迁移为相对路径命令（保留原 timeout），重跑接线不产生重复条目。
    返回合并结果，由调用方原子写回。
    """
    merged = copy.deepcopy(existing) if existing else {}
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        merged["hooks"] = hooks

    registrations = [
        ("SessionStart", "startup", start_cmd, 15),
        ("SessionEnd", "other", end_cmd, 30),
    ]
    for event, matcher, command, timeout in registrations:
        if event not in hooks or not isinstance(hooks[event], list):
            hooks[event] = []
        entries = hooks[event]
        # 找到同 matcher 的注册项，复用而非追加，避免同事件同 matcher 的重复块
        target: Optional[dict] = None
        for entry in entries:
            if isinstance(entry, dict) and entry.get("matcher") == matcher:
                target = entry
                break
        if target is None:
            target = {"matcher": matcher, "hooks": []}
            entries.append(target)
        inner = target.get("hooks")
        if not isinstance(inner, list):
            inner = []
            target["hooks"] = inner

        # 按 command 去重。Windows 下反斜杠/正斜杠路径等价（如
        # `d:/repos/...` 与 `d:\repos\...`），比较前归一化分隔符，
        # 避免历史反斜杠条目与新生成的正斜杠条目被视为不同命令而重复注册。
        def norm(cmd: Optional[str]) -> str:
            return (cmd or "").replace("\\", "/")

        # 迁移旧格式：既有命令以同一相对脚本路径结尾（含 IDE 配置目录，足够
        # 特异）即视为 CodeWiki 历史注册，原地替换为相对路径命令、保留原
        # timeout；随后去重检查会跳过追加。
        suffix = _relative_hook_suffix(command)
        if suffix:
            for h in inner:
                if not isinstance(h, dict):
                    continue
                old = norm(h.get("command"))
                if old and old != norm(command) and old.endswith(suffix):
                    h["command"] = command

        if not any(isinstance(h, dict) and norm(h.get("command")) == norm(command) for h in inner):
            inner.append({"type": "command", "command": command, "timeout": timeout})
    return merged


def _relative_hook_suffix(command: str) -> str:
    """提取 hook 命令结尾带引号的相对脚本路径（含结尾引号）。

    如 ``python ".qoder/hooks/task_session_start.py"`` →
    ``.qoder/hooks/task_session_start.py"``。旧格式条目（绝对路径或
    ``$*_PROJECT_DIR`` 占位符）归一化分隔符后也以同一相对后缀结尾，
    可据此原地迁移。命令无引号脚本路径时返回空串（不迁移）。
    """
    m = re.search(r'"(\.[^"]+/[^"]+\.py)"\s*$', command)
    if not m:
        return ""
    return command[m.start(1) :]


def upsert_agents_section(agents_path: Path) -> bool:
    """把任务记忆会话引导段写入 AGENTS.md（幂等）。

    只动 `<!-- TEAM-MEMORY-TASK:START -->` 到 `<!-- TEAM-MEMORY-TASK:END -->`
    之间的标记块：已存在则整体替换，不存在则追加到文件末尾。绝不触碰标记块
    以外的内容。返回是否发生了变更。
    """
    return _upsert_marker_block(
        agents_path, _TASK_MEMORY_AGENTS_START, _TASK_MEMORY_AGENTS_END, _TASK_MEMORY_AGENTS_SECTION
    )


def upsert_qwenwork_protocol(agents_path: Path) -> bool:
    """把千问办公捕获协议段写入 AGENTS.md（幂等，独立标记块）。

    只动 `<!-- CODEWIKI-QWENWORK:START -->` 到 `<!-- CODEWIKI-QWENWORK:END -->`
    之间的标记块。与 TEAM-MEMORY-TASK 块相互独立：协议段是 QwenWork 专属
    （prompt 接线模式的产物），不随多 IDE 共享引导段的 upsert 被替换。
    """
    return _upsert_marker_block(
        agents_path,
        _QWENWORK_CAPTURE_START,
        _QWENWORK_CAPTURE_END,
        _QWENWORK_CAPTURE_SECTION,
    )


def _upsert_marker_block(agents_path: Path, start: str, end: str, section: str) -> bool:
    """通用标记块 upsert：已存在则替换，否则追加到末尾；块外内容不动。"""
    text = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        before = text[:start_idx]
        after = text[end_idx + len(end) :]
        new_text = before + section + after
    elif text.strip():
        # 追加到末尾，前面留一个空行
        new_text = text.rstrip() + "\n\n" + section + "\n"
    else:
        new_text = section + "\n"
    if new_text == text:
        return False
    safe_write(agents_path, new_text)
    return True


def install_for_ide(repo: str, ide: str) -> dict:
    """为单个 IDE 执行接线全流程，返回接线结果摘要。

    hook 模式（默认）：
    1. 从 codewiki 包内源副本强制拷贝 hook 脚本到 `<repo>/.<ide>/hooks/`，
       拷贝 distill-worker.md 到 `<repo>/.<ide>/agents/`（best-effort）
    2. 合并写入 `<repo>/.<ide>/settings.json` 的 SessionStart/SessionEnd 注册
    3. 向 `<repo>/AGENTS.md` upsert 任务记忆引导段（多 IDE 共享一份，幂等）

    prompt 模式（千问办公）：无 shell hook 机制，仅向 `<repo>/AGENTS.md`
    upsert 任务记忆引导段 + QwenWork 捕获协议段（两个独立标记块，幂等）。
    AGENTS.md 由千问办公作为项目上下文自动加载，等价于 SessionStart 注入；
    会话捕获由 Agent 按协议段执行。
    """
    repo_path = Path(repo)
    if ide not in IDE_SPECS:
        raise IdeWiringError(f"Unknown IDE: {ide!r}. Supported: {', '.join(IDE_SPECS)}")
    spec = IDE_SPECS[ide]

    if spec.get("wiring") == "prompt":
        # prompt 模式：只写 AGENTS.md（引导段 + 专属协议段），无目录/脚本/注册。
        agents_changed = upsert_agents_section(repo_path / "AGENTS.md")
        protocol_changed = upsert_qwenwork_protocol(repo_path / "AGENTS.md")
        return {
            "ide": ide,
            "dir": None,
            "wiring": "prompt",
            "copied": [],
            "settings_written": False,
            "settings_changed": False,
            "agents_changed": agents_changed or protocol_changed,
            "protocol_changed": protocol_changed,
        }

    pkg = _resolve_pkg_sources()

    ide_dir = repo_path / spec["dir"]
    hooks_dir = ide_dir / "hooks"
    agents_dir = ide_dir / spec["agents_dir"]
    hooks_dir.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    # 1a. 强制拷贝 hook 脚本并做 ast 校验
    for name in HOOK_FILES:
        src = pkg / "hooks" / name
        dst = hooks_dir / name
        if not src.is_file():
            raise IdeWiringError(f"Missing hook source in codewiki package: {src}")
        shutil.copy2(src, dst)
        try:
            ast.parse(dst.read_text(encoding="utf-8"))
        except SyntaxError as e:
            raise IdeWiringError(f"Copied hook script is not valid Python: {dst}: {e}")
        copied.append(str(dst.relative_to(repo_path)))

    # 1b. 拷贝 distill-worker subagent 定义（best-effort，缺源文件不阻塞主流程）。
    # 源变体由 IDE_SPECS.agent_file 决定（宿主 frontmatter schema 不同）；
    # 变体缺失时回退默认源。目标文件名始终是 AGENT_FILE。
    if spec.get("copy_agent"):
        src = pkg / "agents" / spec.get("agent_file", AGENT_FILE)
        if not src.is_file():
            src = pkg / "agents" / AGENT_FILE
        dst = agents_dir / AGENT_FILE
        if src.is_file():
            shutil.copy2(src, dst)
            copied.append(str(dst.relative_to(repo_path)))

    # 2. 合并 settings.json（保留无关配置、按 command 去重、原子写回）
    settings_path = ide_dir / spec["settings"]
    existing: Optional[dict] = None
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise IdeWiringError(f"Cannot parse {settings_path}: {e}")
    # command 用项目相对路径，不写机器相关绝对路径
    # （见 START_HOOK_CMD / END_HOOK_CMD 注释）
    start_cmd = START_HOOK_CMD.format(ide_dir=spec["dir"])
    end_cmd = END_HOOK_CMD.format(ide_dir=spec["dir"])
    merged = merge_settings_json(existing, start_cmd, end_cmd)
    settings_changed = merged != existing
    try:
        safe_write(
            settings_path,
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        )
    except FileSystemError as e:
        raise IdeWiringError(str(e))

    # 3. AGENTS.md 引导段 upsert（多 IDE 共享同一仓库，只写一份）
    agents_changed = upsert_agents_section(repo_path / "AGENTS.md")

    return {
        "ide": ide,
        "dir": spec["dir"],
        "copied": copied,
        "settings_written": True,
        "settings_changed": settings_changed,
        "agents_changed": agents_changed,
    }
