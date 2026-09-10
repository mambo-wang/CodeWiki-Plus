### 2026-09-10 21:48

## 2026-09-10 方案讨论（两轮）

需求：同一工作区（git url 唯一标识）下多人/多智能体互通，例：前端 agent 问后端 agent 接口进展。

### 方案 A：git 分片房间（异步，零新基础设施）
- channel_id = sha1(normalize(git remote url))[:12]；存储 `repowiki/.meta/rooms/<channel>/<user_id>.md`，按 sender 分片 append-only（同构于 `tasks/<id>/memories/<user_id>.md`，ADR-0001 文件所有权即 git 级互斥原语）
- 已有地基：user_id (`codewiki/src/config.py:217`)、get_remote_url (`codewiki/cli/git_manager.py:150`)、atomic_write (`codewiki/src/store.py:99`)、file_lock (`codewiki/src/locks.py`)、git_sync session_ff_only/auto_push/sync_check (`codewiki/src/git_sync.py:278/326/226`)
- 工具：agent_post / agent_inbox / agent_presence；已读水位线放 gitignore 本地区（勿进 git）
- 风险：git 历史噪音、user_id 粒度不足（同人多会话）、频道=有 remote 读权限者可见

### 方案 B：LAN websocket + UDP 广播发现（飞秋式，实时）
- 技术上可行：FastAPI+uvicorn 已是依赖 (pyproject.toml:57-58)，websocket 几乎零新依赖
- **核心结论：传输可以实时，agent 不能。** MCP server 是 stdio、随 IDE 会话生灭 (`codewiki/mcp/server.py:211-217`)，server 无法主动把内容推给 LLM。agent 侧最多做到"下次 turn 注入"的准实时；真正自动应答需要常驻 headless agent（另一量级产品）
- 因此实时必须拆两层：**给人的实时**（UI 毫秒到达）+ **给 agent 的准实时**（本地队列 + turn 注入）
- 必须新增独立于 IDE 会话的常驻 daemon（新部署形态，Windows 需处理防火墙/自启）
- 硬问题：Windows 防火墙入站拦截；LAN 开放 websocket = 提示注入通道（需 PSK 配对 + 入站落 draft 走确认闸门 + 默认关闭）

### 收敛方向
传输可插拔（LAN websocket 实时 / git 异步兜底）+ 统一 inbox + 统一已读水位线，上层 agent_post/agent_inbox 不变（单点收敛）。

### 待用户拍板
A 范围（同机多 session vs 跨机 git） / B 出方向是否人工确认闸门 / C 消息是否沉淀为知识 / D 是否真的需要 agent↔agent 实时（反向视角：接口类问题答案 90% 在代码里，前端 agent 自己检索即可，痛点可能是"不知道该问谁/信息在哪"而非通信）

### 待确认
上轮提议把「git 分片房间」设计落成 decision 笔记，用户尚未答复。
