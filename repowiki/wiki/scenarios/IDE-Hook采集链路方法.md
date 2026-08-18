---
title: IDE-Hook采集链路方法
type: Scenario
description: CodeBuddy IDE hook 对话采集链路的 SOP 与禁忌：transcript 索引分片读取、同步采集异步蒸馏、双副本同步、注入可靠性
generated:
  by: codewiki/5.3.0
  at: 2026-08-18 01:50:06+00:00
stale_after: 2026-11-16
aliases:
- IDE-Hook采集链路方法
status: stable
metadata:
  source_notes:
  - notes/2026-08-08-codebuddy-ide-transcript-path-指向的-indexjson-只存元数据真实内容在-messa.md
  - notes/2026-08-12-ide-hook-采用同步采集-异步蒸馏两段式执行模型.md
  - notes/2026-08-12-块剥离正则不要用-行首锚点系统块前可能有-user-前缀.md
  - notes/2026-08-15-codebuddy-hook-有源项目双副本改-task-session-startpy-需同步源副本才随包分发.md
  - notes/2026-08-15-hook-注入的-additionalcontext-是软约束需硬性执行顺序-直接注入任务标题才可靠.md
  - notes/2026-08-15-ide-hook-的-sessionend-envelope-须用-user-角色system-角色会被-transcr.md
  summary: IDE hook 对话采集方法：transcript 索引分片读取、同步采集+异步蒸馏、源/项目双副本同步、additionalContext
    硬性注入与块剥离正则禁忌
  heat: 1
---
## 工作场景
CodeBuddy 等 IDE hook 采集链路（capture_session_end.py → _ide_hook.py → capture_conversation）的方法体系。适用于开发或排查 IDE 对话采集、transcript 解析、hook 注入引导类工作。

## 适用条件
开发/修改 hook 脚本、排查「会话结束未归档对话」、设计 IDE 侧采集与 agent 引导注入。

## 核心 SOP
1. 读 IDE transcript 先识别存储格式：index.json 的 messages 只有 id/role 元数据且存在 messages/ 兄弟目录时，逐个读 messages/<id>.json 并解析嵌套 JSON 字符串的 message 字段——IDE 历史是「索引+分片」结构，假设单文件含完整正文会得到 no usable turns。
2. hook 执行模型保持「同步采集 + 异步蒸馏」：hook 只做落 raw 轻活（subprocess.run timeout=60，失败 {"continue": true} 兜底）；LLM 重活蒸馏永远显式后台触发——IDE 侧延迟可控，重活解耦。
3. 改 hook 脚本先改源副本（codewiki/hooks/）再同步项目副本（.codebuddy/hooks/）：源副本随包分发，项目副本是运行实例，只改项目副本不会随包分发。
4. hook 注入引导要可靠：additionalContext 里写硬性执行顺序（「第一个动作必须是 X，严禁先做 Y」）+ 直接注入任务标题/task_id 等数据——additionalContext 本质是软约束，软措辞（「请立即」）不可靠。

## 判断逻辑
- transcript 噪声过滤只保留 user/assistant 角色；tool/system/thinking/reasoning 均为噪声块。
- envelope 角色选 user：_extract_transcript 只保留 user/assistant，system 角色会被静默丢弃。

## 禁忌与反模式
- 块剥离正则不要用 ^[ \t]* 行首锚点：捕获脚本给行加了 user: 前缀，系统块实际是 user: <tag>；改为任意位置匹配 + DOTALL。
- SessionEnd envelope 不要用 system 角色（内容永远为空且难察觉，属静默丢弃）。

## 关键事实依据
- transcript_path 指向 index.json（仅元数据），真实内容在 messages/<id>.json。
- 「硬性顺序 + 直接注入数据」已验证可靠；「列出任务标题却不列」会让 agent 多走一步 list_tasks。