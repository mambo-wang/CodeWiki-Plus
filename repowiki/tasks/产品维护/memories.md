调研并修复了 capture_conversation 的 task_id 断链：根因是绑定文件（.meta/task_bindings/）不被自动消费，文档声称「绑定被 capture 消费」但实现无自动衔接。已落地 _resolve_task_from_binding 回退逻辑（放在 _content_hash 之前）+ task_source 字段 + 2 个测试（test_task_manager.py 17 passed，test_ide_hook_capture.py 21 passed）。采用宽松语义（绑定存在即盖章，不校验任务 status）。后续可选：若需「只认 active 任务」，在 _resolve_task_from_binding 里加 tasks/.index.json 的 status 查询。

本次会话修复了 task_session_start.py hook 的两个缺口：①新增「硬性执行顺序」段（会话第一个动作必须是弹任务关联框，严禁先探索代码/先回答）；②直接把 active 任务标题+task_id 注入 additionalContext，避免 agent 再自己 list_tasks。改动同时落在源副本 codewiki/hooks/ 与项目副本 .codebuddy/hooks/ 两个文件（内容一致），确保随包分发到所有用户。
