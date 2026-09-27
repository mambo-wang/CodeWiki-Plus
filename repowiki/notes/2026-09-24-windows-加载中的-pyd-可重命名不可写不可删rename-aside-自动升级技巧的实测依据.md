---
type: lesson
title: Windows 加载中的 .pyd 可重命名不可写不可删——rename-aside 自动升级技巧的实测依据
tags:
- lesson
- permissionerror
- winerror
metadata:
  date: 2026-09-24
  confidence_level: weak
  reason: 真机实测事实，探针脚本已验证，待用户确认
  compiled_into:
  - skills/windows-dev-env/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-24 12:37:46+00:00
stale_after: '2027-03-23'
verified:
- by: human:wangbao
  at: '2026-09-24T12:42:32Z'
---

# Windows 加载中 .pyd 文件锁语义实测（2026-09-24 真机探针）

为设计 codewiki-plus 无感知自动升级，用 50 行探针脚本在 Windows 11 + Python 3.12 venv 真机实测了「已被运行中进程加载的 .pyd」的文件操作边界：

| 操作 | 结果 |
|---|---|
| 以写模式打开（r+b） | FAIL：PermissionError [Errno 13] |
| 重命名（os.replace 走再回来） | **OK**：进程无感知，靠句柄继续用旧文件 |
| 删除 | FAIL：PermissionError [WinError 5] |

另实测：`subprocess.Popen(creationflags=DETACHED_PROCESS)` 的子进程在父进程退出后**存活**（3 秒后仍写出文件）。

## 推论

1. **rename-aside 升级可行**：被锁的 .pyd 可重命名到旁边（如 `.old` 后缀），pip 随即可写入新文件；运行中进程靠已映射的句柄继续用旧版本，下次启动加载新版。这是 Chrome 更新器在 Windows 上的同款技巧。
2. **wait-for-exit 兜底路径成立**：detached 子进程等父进程退出后执行 pip install，Windows 文件锁自然释放。
3. **删除不可行**：清理 .old 残留必须推迟到下次启动（此时旧句柄已释放）。

## 设计含义

自动升级采用混合策略：纯 Python 改动走 rename-aside 零等待；原生依赖（tree-sitter 系列）版本变动时退回 wait-for-exit，避免旧原生模块 + 新纯 Python 代码的 ABI 混跑窗口。判断依据：比较 PyPI JSON API 新旧版本 requires_dist 中 tree-sitter 系列的版本约束。
