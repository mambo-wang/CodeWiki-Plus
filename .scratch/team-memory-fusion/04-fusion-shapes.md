status: resolved
type: grilling
title: 融合形态选项对比（内置 / 桥接 / 借鉴）
body: |
  基于 01-03 的事实，对比三种融合形态的可行性与边界，需与用户对话确认倾向。

  ## 待澄清（grilling）
  - 用户更看重：能力深度（内置）还是低耦合与可独立演进（桥接）？
  - 是否接受引入 TS 子项目到以 Python 为主的项目（影响内置形态可行性）。
  - 融合后是否必须保留 MemoryPanel Web 界面。

  ## 交付
  - 三形态对比表：可行性 / 工作量量级（参照 06）/ 与现状冲突 / 演进灵活性。
  - 推荐形态及理由（作为可行性结论的一部分）。

  Blocked by: #1, #2, #3

# 结论（resolved — grilling）

用户决策：**不采用泛化内置/桥接，而是借鉴 TAM "从对话中提取 Wiki/Skill 经验资产" 的能力，在 CodeWiki-CN 自身 Python 体系内实现。**

形态定位 = **聚焦借鉴式（conversation → wiki extraction）**：吸收 TAM 的记忆分层抽取（L0 原始对话 → L1 语义原子 → L2 场景知识块 → L3 画像）与 Skill 提炼思路，落地到 CodeWiki-CN 已有的 `ingest_note`/`repowiki/` 体系，而非引入 TAM 的 Node 服务或 MemoryProxy。

三形态对比（供最终报告）：

| 形态 | 可行性 | 工作量 | 与现状冲突 | 演进灵活 |
|---|---|---|---|---|
| 内置集成 | 中（需补 L0/L3/ACL/Skill） | 高（人月级） | 高（引入 Node 依赖、存储模型差异） | 低 |
| 桥接(MCP/SDK) | 高 | 低-中 | 低 | 高 |
| **借鉴(对话→Wiki)** ✅ | 高 | 中（人周级） | 低（纯 Python，复用现有笔记体系） | 高 |

**推荐**：借鉴式（聚焦对话→Wiki 提取）。理由：保留 CodeWiki-CN Python 单体、复用 `ingest_note` 确认飞轮与 `repowiki/` 产出，避免 Node 依赖；且与 TAM 真正互补的是"记忆分层 + 透明注入"，但用户选择只取其中"对话经验沉淀为 Wiki"这一高价值切片。
