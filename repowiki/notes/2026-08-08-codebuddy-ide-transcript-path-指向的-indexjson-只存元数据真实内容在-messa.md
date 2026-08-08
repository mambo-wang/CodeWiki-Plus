---
type: pitfall
title: "CodeBuddy IDE transcript_path 指向的 index.json 只存元数据，真实内容在 messages/<id>.json"
date: 2026-08-08
related_modules: ["team-memory", "ide-hook", "\"\""]
related_components: []
tags: ["pitfall"]
source_ref: "raw\conv-20260808T145202Z.md"
status: stable
generated: { by: codewiki/5.2.1, at: 2026-08-08T15:19:35Z }
stale_after: 2026-11-06
origin: conversation

---

## 背景

team-memory 的 IDE 采集 hook（capture_session_end.py → _ide_hook.py）依赖 IDE 会话结束事件中的 `transcript_path` 归档对话。该路径指向的 `index.json` 其 `messages` 数组**只含元数据**（id/role/isComplete），不含消息正文；真实内容分散在同级 `messages/<id>.json` 独立文件中，每个文件的 `message` 字段是嵌套 JSON 字符串，内含 `content` 块数组（type 有 text/reasoning/tool-call/tool-result 等）。

## 正确做法

`_load_transcript` 必须先识别这种 index 格式：messages 有 `id` 且无 inline content，且存在 `messages/` 兄弟目录 → 逐个读取 `messages/<id>.json`，解析 `message` JSON 字符串，提取 `content` 块文本。归档知识时只保留 user/assistant 角色，过滤掉 tool/system/thinking/reasoning 等噪声块。

## 根因

旧代码直接把 `index.json` 的元数据列表当作 transcript 返回，capture_conversation 取不到 content → 全部跳过 → 产出 'no usable turns' → 不写任何文件，表现为「结束会话没有归档对话」。

## 适用范围

所有读取 IDE（CodeBuddy/VS Code 系）transcript 的采集逻辑都要注意：IDE 历史文件是「索引 + 分片」存储，不能假设单个 JSON 文件含完整对话正文。
