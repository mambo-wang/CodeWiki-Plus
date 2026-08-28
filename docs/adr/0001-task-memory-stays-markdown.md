# 0001. 任务记忆保持 Markdown，不迁移 JSONL

日期：2026-08-24
状态：已接受

## 背景

任务记忆（`repowiki/tasks/<task_id>/memories.md`）随任务累积只增不减，曾被质疑是否应迁移为 JSONL（业界如 TencentDB-Agent-Memory 的 L0/L1 层用按天分片 JSONL 作 source of truth）。同期暴露的真实问题是读取侧无界加载（get_task_context 全量返回），格式之问由此而起。

## 决策

memories.md 保持 Markdown，不迁移 JSONL；同目录 pending-memories.json 与 tasks/.index.json 同样维持现状。加载问题由"条目结构化 + 截断 + 压缩归档"解决（见《任务记忆存储与加载扩展性设计方案》），不通过换存储格式解决。

## 理由

1. **消费链路无索引层兜底**。TAM 用 JSONL 的前提是旁边有 SQLite FTS/向量索引副本，检索走索引、JSONL 只管追加。CodeWiki 任务记忆量级（单任务几十条）不需要索引层，JSONL 的 O(1) 追加优势无从兑现；现有读改写追加（temp + os.replace）在此量级开销无关紧要。
2. **两类消费者都以 markdown 为原生格式**。LLM 侧：get_task_context 把原文直接注入上下文；人侧：直接打开文件阅读。JSONL 会把多段中文条目的换行全部转义，两类消费者都受损。
3. **跨项目共识：存储格式不重要，加载策略才重要**。TAM（L2 上限 15 块 + L3 ≤1200 字有界注入）、OpenViking（写时分层摘要）、teamai（裸 markdown + 主动检索 + token 预算）三家格式各异，共同点是无一在会话开始时全量加载记忆。

## 后果

- 新增条目带 `### YYYY-MM-DD HH:MM` 时间戳头以支撑切条/截断/压缩；存量裸段落文件运行时回退解析，不做一次性迁移。
- 若未来任务记忆量级出现"需要检索而非加载"的信号（如单任务条目数百条），应优先引入索引层或接入 query_wiki 检索，而非迁移格式。
