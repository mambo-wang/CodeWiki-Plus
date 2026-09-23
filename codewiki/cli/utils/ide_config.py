"""
IDE wiring utilities for CodeWiki hooks/subagents.

将任务记忆 hook/subagent 接线从「仅支持 CodeBuddy」扩展为支持市面上常见的
智能体（Qoder、Claude Code、TRAE）。用户触发创建/启用 hook 时，自动检测项目根目录
存在哪些智能体配置目录（.codebuddy/.qoder/.claude/.gemini/.trae），检测到哪些就为哪些
生成对应 hook 注册与 subagent 定义。

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
from codewiki.mcp.tools.hook_registry import (
    get_agent,
    inject_file_of,
    wiring_of,
)
from codewiki.mcp.prompts import (
    _ACTIVE_SETTLE_END,
    _ACTIVE_SETTLE_START,
    _QWENWORK_CAPTURE_END,
    _QWENWORK_CAPTURE_START,
    _TASK_MEMORY_AGENTS_END,
    _TASK_MEMORY_AGENTS_SECTION,
    _TASK_MEMORY_AGENTS_START,
    _active_settle_section,
)

# ---------------------------------------------------------------------------
# IDE 注册表（核心契约）
# ---------------------------------------------------------------------------
# 每个 IDE 的配置目录、settings.json 文件名、agents 子目录、是否拷贝 distill-worker。
# 新增一个 IDE 只需在此加一行，CLI 命令与 prompt 自动获得支持。
#
# 两种接线档位（单一来源 = codewiki/hooks.yaml 注册表，见
# docs/接线档位选择设计方案.md §3.5；本表不含档位字段，接线前经
# hook_registry.wiring_of() 查注册表，解析顺序 agent > family > 默认）：
#   - "hook"（默认档）：IDE 支持 shell hook 事件（SessionStart/SessionEnd
#     携带 transcript_path 经 stdin 调脚本）——拷脚本、写 settings.json、拷 agent。
#   - "prompt"：宿主无 shell hook 机制，靠上下文注入 + Agent 中介执行
#     （如千问办公：AGENTS.md 自动加载等价 SessionStart；会话捕获由 Agent 按协议
#     调 MCP 工具完成）——只 upsert AGENTS.md 协议段，无 dir/settings/拷贝，
#     且不参与仓库目录自动检测（无仓库标记，仅显式 --ide 触发）。
#
# agent_file（可选）：subagent 定义源文件名。各宿主的 subagent frontmatter
# schema 不同——CodeBuddy 变体用 `mcpServers: [codewiki]` 声明 MCP 授权；
# **勿写 `tools:` 白名单**（写了就只给列表里的工具，MCP 工具全被挡在外面）；
# **勿用 `toolsMCP`**（非官方字段、静默无效）——两者叠加会让 worker 以
# 「0 tool uses 空转」告终（2026-09-11 实测定案）。把 CodeBuddy 版喂给
# claude 家族（Qoder/Claude Code/Gemini CLI）会解析出空工具集、subagent
# 不可用。claude 家族变体省略 tools 行（继承全部工具，含 MCP）——实测 Qoder
# 下显式枚举 `mcp__<server>__<tool>` 不透传给子代理，缺省继承更稳。
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
    # TRAE 家族差异（官方 Hook 规范 docs.trae.cn，2026-09 真机核验）：
    #   - 配置是独立的 .trae/hooks.json（顶层 {"version": 1, "hooks": {...}}），
    #     不是 claude 家族的 settings.json；
    #   - 无 SessionEnd 事件——Stop 在每轮 Query 结束触发且不携带
    #     transcript_path（仅 last_assistant_message），hook 采集无正文可采
    #     （_ide_hook.py 仅 stderr 诊断、不落盘；对话捕获依赖 AGENTS.md
    #     「会话收尾轮」norm 由 Agent 中介采集补漏）；
    #   - matcher 仅对 PreToolUse/PostToolUse/Notification 有效，注册
    #     SessionStart/Stop/UserPromptSubmit 时不写 matcher 字段。
    # SessionStart/UserPromptSubmit 的事件载荷与 claude 家族兼容
    # （含 hookSpecificOutput.additionalContext 注出格式），脚本零改动。
    "trae": {
        "dir": ".trae",
        "settings": "hooks.json",
        "agents_dir": "agents",
        "copy_agent": True,
        "agent_file": "distill-worker.claude.md",
        "format": "trae",
    },
    # qwenwork 无仓库标记目录（dir: None，不参与自动检测）；档位
    # （prompt）不在本表表达，以 codewiki/hooks.yaml 注册表为单源
    # （wiring_of）。主动沉淀固定启用（ADR-0014），不再有叠加字段。
    "qwenwork": {
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

# UserPromptSubmit（技能草稿提示，skill-creator §10）：走包内入口 `python -m`
# 而非物理脚本——IDE 以项目根为工作目录执行 hook 命令，cwd 在 sys.path 上，
# checkout 内或已 pip 安装的 codewiki 包即可 import。命令不含任何路径，
# settings.json 随仓库共享天然可移植。脚本同步读 stdin 事件，内部按
# containment 阈值过滤，命中 `status: draft` 草稿才输出 hookSpecificOutput
# （advisory：只提示、不自动 install）。
PROMPT_HOOK_CMD = "python -m codewiki.mcp._ide_hook --enable"

# hook 事件注册骨架，command 运行时补全为相对路径命令。matcher 语义：
# SessionStart 的 "startup" 匹配会话启动；SessionEnd 的 "other" 匹配任意原因；
# UserPromptSubmit 的空串 matcher 让每条用户指令都过一遍匹配器，是否提示由
# _ide_hook 内部的草稿匹配把关（命中才产生输出，未命中 stdout 为空不注入）。
HOOKS_REGISTRATION = {
    "SessionStart": [
        {"matcher": "startup", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 15}]}
    ],
    "SessionEnd": [
        {"matcher": "other", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 30}]}
    ],
    "UserPromptSubmit": [
        {"matcher": "", "hooks": [{"type": "command", "command": "<cmd>", "timeout": 10}]}
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

    存在 `.codebuddy/.qoder/.claude/.gemini/.trae` 中哪些目录就检测到哪些 IDE——
    即「用户用了哪些智能体就为哪些接线」。prompt 模式（千问办公）在仓库
    无标记目录，不参与自动检测，仅显式 ``--ide qwenwork`` 触发。
    """
    repo_path = Path(repo)
    return [
        name
        for name, spec in IDE_SPECS.items()
        if spec.get("dir") and (repo_path / spec["dir"]).is_dir()
    ]


def merge_settings_json(
    existing: Optional[dict],
    start_cmd: str,
    end_cmd: str,
    spec: Optional[dict] = None,
    capture: bool = True,
) -> dict:
    """幂等合并 CodeWiki 的 hook 注册到现有 settings.json / hooks.json 配置。

    保留 existing 中全部既有键；对 hooks.SessionStart/SessionEnd/UserPromptSubmit
    数组按 command 去重后合并 CodeWiki 注册项，避免重复注册。历史旧格式条目
    （绝对路径、反斜杠路径或 ``$*_PROJECT_DIR`` 占位符形式）指向同一相对脚本
    路径时，原地迁移为相对路径命令（保留原 timeout），重跑接线不产生重复条目。
    UserPromptSubmit（advisory 技能提示）走常量命令 ``PROMPT_HOOK_CMD``——
    ``python -m`` 入口不含路径，无从迁移；matcher 空串 = 每条指令都过匹配器，
    由脚本内部 containment 阈值把关。返回合并结果，由调用方原子写回。

    ``capture=False``（``--capture off``，ADR-0014）时**移除**采集注册
    （claude 家族 SessionEnd / trae 家族 Stop）且不写入——主动沉淀是任务记忆
    唯一通道，采集→蒸馏链路整体停摆；SessionStart（任务关联）与
    UserPromptSubmit（技能提示）不受影响。移除复用 ``unwire_hook_registration``
    的口径：只摘 command 命中 ``end_cmd`` 相对脚本后缀的条目，他人条目原样保留。

    传入 IDE_SPECS 条目 ``spec``（``format: "trae"``）时启用 TRAE 家族差异：
    顶层补 ``version: 1``（TRAE hooks.json 的 schema 版本）；SessionEnd 注册
    映射为 Stop（TRAE 无 SessionEnd 事件，Stop 每轮 Query 结束触发且无
    transcript，_ide_hook 仅 stderr 诊断、不落盘——对话捕获由 AGENTS.md
    「会话收尾轮」norm 承担）；三个注册项不写 matcher（TRAE matcher 仅对
    PreToolSubmit/PostToolSubmit/Notification 有效，省略 = 匹配全部）。
    """
    merged = copy.deepcopy(existing) if existing else {}
    trae = bool(spec and spec.get("format") == "trae")
    if trae:
        # TRAE hooks.json 顶层结构 {"version": 1, "hooks": {...}}
        merged.setdefault("version", 1)
    hooks = merged.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
        merged["hooks"] = hooks

    # capture off：先摘除既有采集注册（幂等，已摘除时无操作）
    if not capture:
        _remove_capture_registration(hooks, end_cmd)

    if trae:
        registrations = [
            # TRAE 无 SessionEnd：Stop 每轮 Query 结束触发，无 transcript_path，
            # _ide_hook 仅 stderr 诊断、不落盘（对话捕获走 Agent 收尾 norm）。
            ("SessionStart", None, start_cmd, 15),
            ("UserPromptSubmit", None, PROMPT_HOOK_CMD, 10),
        ]
        if capture:
            registrations.insert(1, ("Stop", None, end_cmd, 30))
    else:
        registrations = [
            ("SessionStart", "startup", start_cmd, 15),
            # matcher 空串：UserPromptSubmit 的匹配对象是用户指令文本，空串 =
            # 每条都触发（区别于 SessionStart 的 "startup" 只匹配会话启动）。
            # 同步执行（IDE 要等 stdout 的 hookSpecificOutput），timeout 10 足够。
            ("UserPromptSubmit", "", PROMPT_HOOK_CMD, 10),
        ]
        if capture:
            registrations.insert(1, ("SessionEnd", "other", end_cmd, 30))
    for event, matcher, command, timeout in registrations:
        if event not in hooks or not isinstance(hooks[event], list):
            hooks[event] = []
        entries = hooks[event]
        # 找到同 matcher 的注册项，复用而非追加，避免同事件同 matcher 的重复块。
        # matcher 为 None（trae 格式不写 matcher）时复用第一个条目——TRAE 的
        # matcher 对这三个事件本就无效，复用可兼容用户手抄的带 matcher 历史
        # 条目，避免同命令注册两遍被 IDE 双重触发。
        target: Optional[dict] = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if matcher is None or entry.get("matcher") == matcher:
                target = entry
                break
        if target is None:
            target = {"matcher": matcher, "hooks": []} if matcher is not None else {"hooks": []}
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


def _remove_capture_registration(hooks: dict, end_cmd: str) -> None:
    """capture off 时从 hooks 映射中摘除采集注册（原地修改，幂等）。

    只摘 command 归一化后命中 ``end_cmd`` 相对脚本后缀的条目（兼容历史
    绝对路径/反斜杠旧格式）；条目内命令被删空才移除该条目，事件数组被
    删空才移除该事件键，全部事件键删空才移除 ``hooks`` 键本身。他人条目
    一律不动。trae 家族的采集注册在 Stop 事件下，同样以 end_cmd 后缀命中。
    """
    suffix = _relative_hook_suffix(end_cmd)

    def norm(cmd: Optional[str]) -> str:
        return (cmd or "").replace("\\", "/")

    for event in list(hooks.keys()):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        new_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                new_entries.append(entry)
                continue
            inner = entry.get("hooks")
            if not isinstance(inner, list):
                new_entries.append(entry)
                continue
            kept = [
                h
                for h in inner
                if not (isinstance(h, dict) and suffix and norm(h.get("command")).endswith(suffix))
            ]
            if len(kept) == len(inner):
                new_entries.append(entry)
                continue
            if kept:
                entry["hooks"] = kept
                new_entries.append(entry)
            # kept 为空：条目内全是采集命令 → 整条移除
        if new_entries:
            hooks[event] = new_entries
        else:
            del hooks[event]


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


def unwire_hook_registration(repo: str, ide: str) -> bool:
    """换档清理（设计方案 §3.10）：移除配置文件中属于 CodeWiki 的 hook 注册条目。

    ``hook → prompt`` 换档时调用。只删 command 命中我们相对脚本后缀的条目
    （复用 ``_relative_hook_suffix`` 口径，归一化路径分隔符后 endswith 匹配，
    兼容历史绝对路径/反斜杠/``$*_PROJECT_DIR`` 旧格式条目）与常量命令
    ``PROMPT_HOOK_CMD``（``python -m`` 入口无路径，按整串归一化后相等匹配）；
    他人条目与 settings 其他键一律原样保留（沿用 ``merge_settings_json`` 的
    preserve-all 契约）。

    **绝不整段清空 ``hooks`` 键**：只从命中的条目内部摘除我们的命令；某条目
    内命令被删空才移除该条目，某事件数组被删空才移除该事件键，全部事件键
    都删空才移除 ``hooks`` 键本身——每一步都只因我们自己的条目消失而发生。

    配置文件不存在 / 无 ``hooks`` 键 / 无我们的条目 → 无操作返回 False
    （重跑幂等：第二次不产生任何写入）。返回是否发生了变更。
    """
    spec = IDE_SPECS.get(ide)
    if not spec or not spec.get("dir"):
        return False
    settings_path = Path(repo) / spec["dir"] / spec["settings"]
    if not settings_path.is_file():
        return False
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise IdeWiringError(f"Cannot parse {settings_path}: {e}")
    if not isinstance(data, dict):
        return False
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return False

    def norm(cmd: Optional[str]) -> str:
        # Windows 下反斜杠/正斜杠等价，与 merge_settings_json 的去重口径一致
        return (cmd or "").replace("\\", "/")

    # 我们的命令特征：两个相对脚本后缀 + 常量 PROMPT_HOOK_CMD
    suffixes = [
        s
        for s in (
            _relative_hook_suffix(START_HOOK_CMD.format(ide_dir=spec["dir"])),
            _relative_hook_suffix(END_HOOK_CMD.format(ide_dir=spec["dir"])),
        )
        if s
    ]
    prompt_cmd = norm(PROMPT_HOOK_CMD)

    def is_ours(cmd) -> bool:
        if not isinstance(cmd, str):
            return False
        c = norm(cmd)
        return c == prompt_cmd or any(c.endswith(s) for s in suffixes)

    changed = False
    for event in list(hooks.keys()):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        new_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                new_entries.append(entry)
                continue
            inner = entry.get("hooks")
            if not isinstance(inner, list):
                new_entries.append(entry)
                continue
            kept = [h for h in inner if not (isinstance(h, dict) and is_ours(h.get("command")))]
            if len(kept) == len(inner):
                # 未命中我们的命令：条目原样保留（他人条目零改动）
                new_entries.append(entry)
                continue
            changed = True
            if kept:
                # 混合条目：只摘除我们的命令，他人命令原样保留
                entry["hooks"] = kept
                new_entries.append(entry)
            # kept 为空：条目内全是我们自己的命令 → 整条移除
        if new_entries:
            hooks[event] = new_entries
        else:
            # 事件数组被删空（原本只有我们的条目）→ 移除该事件键
            del hooks[event]
    if changed and not hooks:
        # 所有事件键都因移除我们的条目而消失 → hooks 键本身也还原掉
        del data["hooks"]
    if not changed:
        return False
    try:
        safe_write(
            settings_path,
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        )
    except FileSystemError as e:
        raise IdeWiringError(str(e))
    return True


def upsert_agents_section(agents_path: Path) -> bool:
    """把任务记忆会话引导段写入 AGENTS.md（幂等）。

    只动 `<!-- TEAM-MEMORY-TASK:START -->` 到 `<!-- TEAM-MEMORY-TASK:END -->`
    之间的标记块：已存在则整体替换，不存在则追加到文件末尾。绝不触碰标记块
    以外的内容。返回是否发生了变更。
    """
    return _upsert_marker_block(
        agents_path, _TASK_MEMORY_AGENTS_START, _TASK_MEMORY_AGENTS_END, _TASK_MEMORY_AGENTS_SECTION
    )


def upsert_active_settle_protocol(agents_path: Path, ide: str) -> bool:
    """恒渲染 CODEWIKI-ACTIVE-SETTLE 块（ADR-0014 固定启用）+ 一次性迁移。

    泛化取代旧 ``upsert_qwenwork_protocol``（旧 CODEWIKI-QWENWORK 块，设计方案 §3.9）：

    - **固定启用**：主动沉淀不再有开关（ADR-0014），本函数恒 upsert 新块。
    - **一次性迁移**：upsert 时发现旧 CODEWIKI-QWENWORK 块 → 整体删除后写
      新块，仓库内不再残留旧标记。
    - **宿主专属小节**：新块正文第 ③ 节按注册表 ``agents[].protocol`` 追加
      （qwenwork 的会话历史 API 小节由旧块正文迁移而来，信息不丢）。

    只动两个协议块的标记区间，块外内容一律不改。返回是否发生了变更。
    """
    # on：一次性迁移（旧 QWENWORK 块存在则整体删除），再 upsert 新块
    agent = get_agent(ide) or {}
    protocol = str(agent.get("protocol") or "")
    section = _active_settle_section(protocol)
    migrated = _remove_marker_block(agents_path, _QWENWORK_CAPTURE_START, _QWENWORK_CAPTURE_END)
    changed = _upsert_marker_block(agents_path, _ACTIVE_SETTLE_START, _ACTIVE_SETTLE_END, section)
    return migrated or changed


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


def _remove_marker_block(agents_path: Path, start: str, end: str) -> bool:
    """通用标记块删除：整块删除（含 START/END 标记本身）；块外内容不动。

    块不存在或文件不存在 → 无操作返回 False。只在删除的块**自身边界**上收敛
    空行（与 upsert 追加时留的 ``\\n\\n`` 前缀对称：块存在时恰好还原到块追加
    前的空行数量），不折叠文件其余部分的空行结构。
    """
    if not agents_path.exists():
        return False
    text = agents_path.read_text(encoding="utf-8")
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return False
    after_idx = end_idx + len(end)
    # 边界收敛：块前方若有≥2 个换行（含 upsert 追加留的空行）吃掉一个；
    # 块后方紧跟的换行一并带走。
    strip_start = start_idx
    if start_idx >= 2 and text[start_idx - 2 : start_idx] == "\n\n":
        strip_start -= 1
    if after_idx < len(text) and text[after_idx] == "\n":
        after_idx += 1
    new_text = text[:strip_start] + text[after_idx:]
    if new_text == text:
        return False
    safe_write(agents_path, new_text)
    return True


def install_for_ide(
    repo: str,
    ide: str,
    capture: Optional[bool] = None,
    inject_file: Optional[str] = None,
) -> dict:
    """为单个 IDE 执行接线全流程，返回接线结果摘要。

    档位自动判定（见 docs/接线档位选择设计方案.md §3.6）：按注册表
    ``wiring_of(ide)`` 判定——支持 SessionStart 的宿主走 hook 档，不支持的
    （qwenwork）走 prompt 档，无手动覆盖（--mode 已移除）。

    采集开关（ADR-0014）：``capture=None`` 默认 on；显式 False（CLI
    ``--capture off``）时移除 SessionEnd（trae 为 Stop）采集注册且不写入，
    SessionStart（任务关联）与 UserPromptSubmit（技能提示）保留，hook 脚本
    与 distill-worker 照常拷贝（存量 raw 积压仍需补蒸馏）。主动沉淀固定
    启用，CODEWIKI-ACTIVE-SETTLE 块恒渲染。

    ``inject_file``：注入文件路径（相对仓库根），默认注册表 ``inject_file_of(ide)``。

    hook 档：
    1. 从 codewiki 包内源副本强制拷贝 hook 脚本到 `<repo>/.<ide>/hooks/`，
       拷贝 distill-worker.md 到 `<repo>/.<ide>/agents/`（best-effort）
    2. 合并写入 hook 注册：claude 家族写 `<repo>/.<ide>/settings.json`
       （SessionStart/SessionEnd/UserPromptSubmit）；trae 家族写
       `<repo>/.trae/hooks.json`（顶层 version: 1，SessionStart/Stop/
       UserPromptSubmit，不写 matcher）
    3. 向注入文件（默认 `<repo>/AGENTS.md`）upsert 任务记忆引导段
       （多 IDE 共享一份，幂等）

    prompt 档（千问办公）：无目录/脚本/注册，只动注入文件——upsert 任务
    记忆引导段 + 主动沉淀协议段（两个独立标记块，幂等）。注入文件由宿主
    作为项目上下文自动加载，等价于 SessionStart 注入；会话捕获由 Agent
    按协议段执行。
    """
    repo_path = Path(repo)
    if ide not in IDE_SPECS:
        raise IdeWiringError(f"Unknown IDE: {ide!r}. Supported: {', '.join(IDE_SPECS)}")
    spec = IDE_SPECS[ide]

    # 档位：hooks.yaml 注册表为单源（agent > family > 默认 "hook"），
    # 自动判定，无手动覆盖。
    wiring = wiring_of(ide)
    # 采集开关：None = 默认 on；显式 False = CLI --capture off（ADR-0014）
    capture_on = True if capture is None else bool(capture)
    # 注入文件：显式覆盖 > 注册表解析（默认 AGENTS.md）。--inject-file 可能
    # 指向尚不存在的子目录（如 docs/），先建父目录再写。
    inject_path = repo_path / (inject_file or inject_file_of(ide))
    inject_path.parent.mkdir(parents=True, exist_ok=True)

    if wiring == "prompt":
        # prompt 档：只写注入文件（引导段 + 主动沉淀协议段），无目录/脚本/注册。
        # 主动沉淀固定启用（ADR-0014），协议段恒渲染（并把遗留的旧
        # CODEWIKI-QWENWORK 块一次性迁移为新块）。

        # 换档清理（设计方案 §3.10）：历史 hook 接线残留的注册条目必须移除
        # ——只删 command 命中相对脚本后缀（或常量 PROMPT_HOOK_CMD）的条目，
        # 他人条目与 settings 其他键原样保留；条目本就不存在时为无操作
        # （幂等，第二次跑不产生写入）。
        unwired = unwire_hook_registration(repo, ide)
        agents_changed = upsert_agents_section(inject_path)
        protocol_changed = upsert_active_settle_protocol(inject_path, ide)
        return {
            "ide": ide,
            "dir": None,
            "wiring": "prompt",
            "capture": capture_on,
            "copied": [],
            "settings_written": False,
            "settings_changed": False,
            "agents_changed": agents_changed or protocol_changed,
            "protocol_changed": protocol_changed,
            "unwired": unwired,
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

    # 2. 合并 settings.json / hooks.json（保留无关配置、按 command 去重、原子写回）
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
    merged = merge_settings_json(existing, start_cmd, end_cmd, spec=spec, capture=capture_on)
    settings_changed = merged != existing
    try:
        safe_write(
            settings_path,
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        )
    except FileSystemError as e:
        raise IdeWiringError(str(e))

    # 3. 注入文件引导段 upsert（多 IDE 共享同一仓库，只写一份；默认
    #    AGENTS.md，--inject-file 可覆盖）。主动沉淀固定启用（ADR-0014）：
    #    hook 档宿主（如 trae）「hook 读 + prompt 写」共存，ACTIVE-SETTLE
    #    块恒渲染（渲染逻辑与 prompt 档同一函数）。
    agents_changed = upsert_agents_section(inject_path)
    protocol_changed = upsert_active_settle_protocol(inject_path, ide)
    agents_changed = agents_changed or protocol_changed

    return {
        "ide": ide,
        "dir": spec["dir"],
        "wiring": "hook",
        "capture": capture_on,
        "copied": copied,
        "settings_file": spec["settings"],
        "settings_written": True,
        "settings_changed": settings_changed,
        "agents_changed": agents_changed,
        "protocol_changed": protocol_changed,
        # hook 档不存在换档清理对象：注册/产物本次都会被重建（强制覆盖拷贝），
        # unwired 恒为 False。
        "unwired": False,
    }
