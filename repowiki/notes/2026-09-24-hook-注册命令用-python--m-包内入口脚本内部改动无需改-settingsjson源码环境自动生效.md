---
type: architecture
title: hook 注册命令用 python -m 包内入口：脚本内部改动无需改 settings.json，源码环境自动生效
tags:
- architecture
- codewiki
- userpromptsubmit
metadata:
  date: 2026-09-24
  confidence_level: weak
  task_id: 他山之石
  source_session: 1b5f06c022ab4dcd9dfabc02661535f2
  related_modules:
  - cli/utils/ide_config
  - mcp/_ide_hook
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-2-670adf.md
  scene: hook 脚本加新分支后用户问配置要不要改
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.0
  at: 2026-09-24 12:57:28+00:00
stale_after: '2027-09-25'
origin: conversation
verified:
- by: human:iamwangbao
  at: '2026-09-25T13:32:45Z'
---

## Background

UserPromptSubmit hook 脚本（`_ide_hook.py`）新增 active-settle 提醒分支后，用户问 settings.json 的 hook 配置是否需要同步改。结论：不用改。

## 结构事实

CodeWiki 注册 hook 的 command 是 `python -m codewiki.mcp._ide_hook --enable`——跑的是**包内入口**，不是拷贝出来的物理脚本。因此：

1. **源码 checkout 环境**：命令每次执行都 import 当前 checkout 的包，脚本内部新增分支自动生效（active-settle 提醒提交后本会话即触发注入，即为真机证明）。
2. **其他接线仓库**：注册同样是这条 `python -m` 命令，只要环境的 codewiki 包升级到含改动的版本，行为自动跟上。
3. **唯一例外**：环境装的是旧版 pip 包（而非源码 checkout）时，需 `pip install -U` 才能拿到新分支——配置文件本身永远不用碰。

## Rationale

这是当初选 `python -m` 入口而非物理拷贝脚本的设计收益（`ide_config.py:134-139` 的设计注释写明）。判断「hook 行为更新要不要动配置」时先看注册命令形态：包内入口 → 只升级包；物理脚本路径 → 需重新分发脚本。
