---
type: Conversation
title: "conversation 20260829T000612Z"
status: distilled
stale_after: 2026-11-27
generated: { by: codewiki/5.4.5, at: 2026-08-29T00:06:12Z }
captured_at: "2026-08-29T00:06:12Z"
content_hash: "sha256:60b472b8121e3acf6453430b5801b065ed93aa910d33cc10850a0227edaf1c92"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=3"
keep_raw: false
link_to: ""
source_session: "390d77219f6f4ee4a1f8ae9d7a256b37"
turn_count: 10
---

# Conversation Transcript

user: @CodeWiki-Plus系列9：仓库多了，知识该放哪——Harness工作区与Wiki的两种布局.md:45-54  在第二行repowiki上边添加一行.codebuddy/ 作用是存放项目级Skill Rule Agent Hooks Command等工具
user: <question>是否将本次会话关联到某个进行中的任务？（用于跨会话任务记忆）</question>
<answers>
跳过(本次会话不做任务关联，直接开始干活)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 跳过任务关联。现在处理你的编辑请求，先读取文件确认当前内容。
assistant: 已在 `repowiki/` 上方插入 `.codebuddy/` 行：

```45:50:docs/articles/CodeWiki-Plus系列9：仓库多了，知识该放哪——Harness工作区与Wiki的两种布局.md
CodeWiki-Plus-Harness/          ← harness 主仓库（独立 git，提交稳定）
├── .codebuddy/                 ← 项目级 Skill / Rule / Agent / Hooks / Command 等工具资产
├── repowiki/                   ← 产品级 Wiki：产品概述、各仓业务概述、仓库导航
│   └── wiki/repo-map.md        ← 仓库导航页（检索入口）
├── AGENTS.md                   ← Agent 工作约定（检索路由、提交纪律）
├── bootstrap.ps1 / .sh         ← 一键初始化：克隆全部业务子仓
```

对齐方式与相邻行保持一致，注释明确了其存放项目级工具资产的作用。
user: @prompts.py:227-229  登记完之后不要自动生成wiki
assistant: 先读取该文件相关区域确认上下文。
assistant: 检查同一文件中是否还有其他自动生成 wiki 的指引。
assistant: 第 258 行还有一处"登记后建 wiki"的指引，查看上下文。
assistant: 用户意图是登记后不自动生成 wiki。`add_workspace_repo` prompt 的步骤 4 也提到建 Wiki，一并改为不自动生成。
assistant: Lint 报错均为既有问题（第 1326 行等），与本次修改无关，无新增错误。

已完成，登记后不再自动生成 wiki，共改两处：

1. **`_prompt_init_workspace`（init-workspace prompt）步骤 4**：标题改为「登记业务仓」，删除自动 `init_wiki / analyze_repo / analyze_workspace` 的步骤，明确改为"登记完成后**不要自动生成 wiki**，等用户显式要求时再生成"。
2. **`_prompt_add_workspace_repo`（add-workspace-repo prompt）步骤 4**：原"后续（可选但推荐）建仓库级 Wiki"改为"登记完成后**不要自动生成 wiki**：不调用 init_wiki / analyze_repo，等用户显式要求时再建"。

两处语义保持一致：登记（`add_workspace_repo`）只负责登记表 + 克隆，wiki 生成全部改为显式触发。
