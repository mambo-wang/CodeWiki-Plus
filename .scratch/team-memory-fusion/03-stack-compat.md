status: resolved
type: research
title: 技术栈与运行形态兼容性
body: |
  评估 Team-Agent-Memory（TypeScript + Python 多子项目）与 CodeWiki-CN（Python 为主）在技术栈与运行形态上的兼容性。

  ## 调研要点
  - 依赖与运行环境：Team-Agent-Memory 各子项目依赖（Node 版本、Python 版本、向量库 / 数据库如 PostgreSQL、Milvus）。
  - 部署形态：Docker 组合、本地运行、是否有独立服务端口 / MCP server。
  - 与 CodeWiki-CN 现有依赖（requirements.txt / pyproject.toml / docker/）的冲突或叠加成本。
  - 数据持久化后端：两者各自用什么存储，融合时能否共用。

  ## 交付
  - 兼容性矩阵：维度（语言 / 依赖 / 存储 / 部署）x 结论（兼容 / 需适配 / 不可行）。
  - 对“内置集成”与“桥接”两种形态分别的运行形态成本提示。
