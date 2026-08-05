status: resolved
type: research
title: Team-Agent-Memory 能力盘点
body: |
  盘点 D:/repos/Team-Agent-Memory（TencentDB Agent Memory）各子项目提供的记忆 / 经验能力，明确接口与边界。

  ## 调研要点
  - MemoryCore：记忆存储与检索的核心数据模型（L0-L3 分层、Skill、Asset/资源、ACL/用户隔离）与 API 形态。
  - MemoryKnowledge：Wiki / CodeGraph 知识沉淀与 MCP 暴露方式（与 CodeWiki-CN 的 `codewiki/` 重叠部分）。
  - MemoryProxy：透明代理如何把记忆注入 LLM 对话，触发入口与协议。
  - MemoryPanel：Web UI 提供的能力范围（是否与融合强相关）。
  - sdk：TS / Py SDK 的调用面，作为桥接形态的关键入口。

  ## 交付
  - 一份能力清单（表格：子项目 / 能力 / 对外接口 / 是否 CodeWiki-CN 已有 / 融合价值高/中/低）。
  - 关键接口的调用示例（SDK / MCP / HTTP）。
