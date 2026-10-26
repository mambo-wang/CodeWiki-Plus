---
name: codewiki-distill-conversations
description: "检测到 repowiki/raw/ 存在未蒸馏的已采集对话积压时使用（如会话开始提示 pending_raw_count > 0）。把已采集对话蒸馏为双轨产物：notes（通用经验笔记）与 memories（任务进度记忆）。宿主 Agent 充当 LLM：distill_conversation(mode=prepare) 取 transcript → Agent 提取知识 → mode=submit 交回做去重/草稿入库/记忆落盘/评审。全程本地闭环，蒸馏产出的笔记须 confirm_note 确认。"
# model-invocable
---

# 蒸馏对话提取记忆和经验

检测到 repowiki/raw/ 存在未蒸馏的已采集对话积压时使用（如会话开始提示 pending_raw_count > 0）。把已采集对话蒸馏为双轨产物：notes（通用经验笔记）与 memories（任务进度记忆）。宿主 Agent 充当 LLM：distill_conversation(mode=prepare) 取 transcript → Agent 提取知识 → mode=submit 交回做去重/草稿入库/记忆落盘/评审。全程本地闭环，蒸馏产出的笔记须 confirm_note 确认。

调用 MCP 获取完整工作流并按其执行：

```
get_prompt(name="distill-conversations", arguments={"repo_path": "."})
```

返回的工作流包含分阶段指引，逐步照做即可。
不要凭记忆执行——模板真源在 `codewiki/mcp/prompts.py`，以 `get_prompt` 返回内容为准。
本技能可由模型按需自动调用（无 disable-model-invocation），也可由用户显式调用 /codewiki-distill-conversations 触发。
