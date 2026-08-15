---
name: CodeWiki任务记忆系统
overview: 参考 TencentDB-Agent-Memory 设计，为 CodeWiki-Plus 增加"任务(Task)级记忆系统"：用户新建/选择任务 → 对话采集与蒸馏关联 task_id → 产出任务记忆（repowiki/tasks/）与任务关联的经验 notes → 新会话选择任务时通过 get_task_context 工具 + hook 注入任务记忆与经验。
todos:
  - id: task-storage-tools
    content: 实现 task_manager.py：任务 CRUD、set_session_task、add_task_memory、get_task_context 与 repowiki/tasks 存储结构
    status: completed
  - id: capture-task-link
    content: capture_conversation 与 _ide_hook 增加 task_id 参数，写入 raw frontmatter 与索引
    status: completed
    dependencies:
      - task-storage-tools
  - id: distill-dual-track
    content: 扩展 distill_conversation：透传 task_id、_DISTILL_SYSTEM 增加 memory 提取并落盘任务记忆
    status: completed
    dependencies:
      - capture-task-link
  - id: retrieval-injection
    content: ingest_note/query_wiki 增加 task_id 字段与过滤，get_task_context 聚合关联经验 notes
    status: completed
    dependencies:
      - distill-dual-track
      - task-storage-tools
  - id: registry-wiring
    content: registry.py 注册新工具，prompts.py 增加任务工作流引导，AGENTS.md 注入活跃任务上下文
    status: completed
    dependencies:
      - retrieval-injection
      - task-storage-tools
  - id: tests-verify
    content: 新增 tests/test_task_manager.py，用 [mcp:codewiki] 端到端验证任务创建、采集关联、蒸馏记忆与检索过滤
    status: completed
    dependencies:
      - registry-wiring
---

