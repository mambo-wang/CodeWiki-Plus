# 操作日志

> 本文件为追加写入的操作记录，由系统自动维护

## 2026-08-25
* **ingest_note**: 添加笔记: 聚合/doctrine 阈值等运行参数通过 repowiki/schema.yaml conventions.aggregation 覆盖，不改 py 源码默认值
* **ingest_note**: 添加笔记: doctrine 不会自动注入 Agent 上下文：唯一通道是 query_wiki(mode='overview')
* **ingest_note**: 添加笔记: 移除 doctrine 备份机制：.backup 冗余且备份文件会污染检索索引
* **ingest_note**: 添加笔记: MCP 参数长度受限时蒸馏 submit 走文件侧通道：Python 脚本直接调 handle_distill_conversation
* **ingest_note**: 添加笔记: 蒸馏时无知识密度的对话也提交空结果，否则 raw 无法归档清理
* **ingest_note**: 添加笔记: 知识摄入到自动检索链路：ingest_note 自动写索引、close_session 兜底终态
* **analyze_repo**: 分析仓库 CodeWiki-CN，1561 个组件
* **analyze_repo**: 分析仓库 CodeWiki-CN，1561 个组件

## 2026-08-24
* **lint_wiki**: 检查完成: 0 个问题
* **lint_wiki**: 检查完成: 57 个问题
* **lint_wiki**: 检查完成: 103 个问题
* **lint_wiki**: 检查完成: 103 个问题
* **ingest_note**: 添加笔记: Windows GBK 控制台编码导致 CLI 输出与 twine 发布崩溃
* **ingest_note**: 添加笔记: 配置合并的 Python 坑：dict 浅拷贝污染原配置 + hooks.get(event, []) 未写回
* **ingest_note**: 添加笔记: GitHub API 直连被阻时用 PowerShell Invoke-RestMethod 走系统网络栈，token 从 git 凭据管理器提取
* **ingest_note**: 添加笔记: MCP prompt 与 AGENTS.md 是同一约定的两个载体：静态常驻注入 vs 按需可查询
* **close_session**: 会话关闭
* **ingest_note**: 添加笔记: install-hooks 幂等去重在 Windows 路径分隔符下失效
* **ingest_note**: 添加笔记: smoke test 用临时 output_dir 污染真实仓库缓存导致落盘错位
* **ingest_note**: 添加笔记: lint_wiki 支持 fix=true 自愈过期索引
* **ingest_note**: 添加笔记: patch 已有 frontmatter 路径缺 aliases 默认键
* **ingest_note**: 添加笔记: 对话归档原样保留用户消息密钥导致 push 被 GitHub 密钥扫描拦截
* **ingest_note**: 添加笔记: raw 索引 .index.json 的 task_id 带字面引号导致按任务过滤漏检
* **ingest_note**: 添加笔记: health_score 为扣分制：error-10/warning-3/info-1
* **ingest_note**: 添加笔记: 子代理报告「全绿」不可信：lastfailed 缓存空 ≠ 真全绿，须自己实跑验证
* **ingest_note**: 添加笔记: telemetry 采用 per-user jsonl 文件：零冲突设计的承重墙
* **ingest_note**: 添加笔记: 孤儿分支不是「部分文件单独分支」，.codewiki 二进制缓存救不了冲突
* **ingest_note**: 添加笔记: 多 IDE hook 支持按家族归并：31 个智能体收敛为 3 家族 schema
* **ingest_note**: 添加笔记: 测试多 helper 各写一次 jsonl 会互相全量覆盖，须 append-merge 且不依赖固定 user 文件名
* **ingest_note**: 添加笔记: task_bindings 绑定文件改为一次性消费凭证：成功落盘后删除 + supersede 继承旧 task_id
* **ingest_note**: 添加笔记: Agent 表述必须诚实区分「已知事实」与「推测」，不能把假设当依据
* **ingest_note**: 添加笔记: 修复顺序类 bug 先看数据流时序：fix 块后置导致 broken_links 基于旧索引计算
* **ingest_note**: 添加笔记: ruff 升级规则集变宽导致 CI 大面积红：显式 select 钉住窄默认，不顺风修宽规则
* **ingest_note**: 添加笔记: 单次 commit 业务 review 工具选型：mattpocock code-review 走 Spec 轴，需求来源可绕 setup
* **ingest_note**: 添加笔记: frontmatter deep module 重构四决策：路由收进 module、原地扩展、字节级兼容、先 reader 后 writer
* **ingest_note**: 添加笔记: retrieval_stats.db 放 repowiki/.meta 而非 .codewiki 的四个理由
* **ingest_note**: 添加笔记: OpenViking 借鉴三原则：借分层不借 LLM、借模式不借 hook、借粒度不借无闸门
* **ingest_note**: 添加笔记: TAM L0-L3 记忆管线对照：CodeWiki 已有 L0/L1，空白在 L2 场景聚合与 L3 Doctrine
* **edit_doc_file**: 更新 任务记忆系统设计方法.md (str_replace)
* **edit_doc_file**: 更新 IDE-Hook采集链路方法.md (str_replace)
* **edit_doc_file**: 更新 Wiki页面生成约定与数据结构.md (str_replace)
* **edit_doc_file**: 更新 MCP-Server薄壳架构与参数约定.md (str_replace)
* **edit_doc_file**: 更新 对话蒸馏管线与raw暂存区.md (str_replace)
* **edit_doc_file**: 更新 任务记忆系统设计方法.md (str_replace)
* **edit_doc_file**: 更新 IDE-Hook采集链路方法.md (str_replace)
* **edit_doc_file**: 更新 Wiki页面生成约定与数据结构.md (str_replace)
* **edit_doc_file**: 更新 MCP-Server薄壳架构与参数约定.md (str_replace)
* **edit_doc_file**: 更新 对话蒸馏管线与raw暂存区.md (str_replace)
* **edit_doc_file**: 更新 任务记忆系统设计方法.md (str_replace)
* **edit_doc_file**: 更新 IDE-Hook采集链路方法.md (str_replace)
* **edit_doc_file**: 更新 Wiki页面生成约定与数据结构.md (str_replace)
* **edit_doc_file**: 更新 MCP-Server薄壳架构与参数约定.md (str_replace)
* **edit_doc_file**: 更新 对话蒸馏管线与raw暂存区.md (str_replace)
* **edit_doc_file**: 更新 任务记忆系统设计方法.md (str_replace)
* **edit_doc_file**: 更新 IDE-Hook采集链路方法.md (str_replace)
* **edit_doc_file**: 更新 Wiki页面生成约定与数据结构.md (str_replace)
* **edit_doc_file**: 更新 MCP-Server薄壳架构与参数约定.md (str_replace)
* **edit_doc_file**: 更新 对话蒸馏管线与raw暂存区.md (str_replace)
* **write_doc_file**: 创建 发布与依赖治理方法.md

## 2026-08-23
* **ingest_note**: 添加笔记: hook 采集机制仅正式接线 CodeBuddy，README 措辞用「仅接线支持」
* **lint_wiki**: 检查完成: 335 个问题
* **ingest_note**: 添加笔记: 会话启动时的 query_wiki/蒸馏等重操作委托 subagent 执行，避免阻塞用户正常使用
* **lint_wiki**: 检查完成: 339 个问题
* **lint_wiki**: 检查完成: 339 个问题
* **analyze_repo**: 分析仓库 CodeWiki-CN，1482 个组件
* **analyze_repo**: 分析仓库 CodeWiki-CN，1482 个组件
* **edit_doc_file**: 更新 MCP_Tools_Quality.md (str_replace)
* **edit_doc_file**: 更新 MCP_Tools_Quality.md (str_replace)
* **edit_doc_file**: 更新 MCP_Tools_Quality.md (str_replace)
* **edit_doc_file**: 更新 MCP_Prompts.md (str_replace)
* **edit_doc_file**: 更新 MCP_Prompts.md (str_replace)
* **edit_doc_file**: 更新 MCP_Prompts.md (str_replace)
* **edit_doc_file**: 更新 MCP_Prompts.md (str_replace)
* **lint_wiki**: 检查完成: 13 个问题
* **close_session**: 会话关闭
* **ingest_note**: 添加笔记: distill-worker subagent 定义随包发布，hook 启用时自动拷贝到项目 .codebuddy/agents/
* **ingest_note**: 添加笔记: 多 IDE hook 自动检测接线：IDE 注册表驱动 + codewiki install-hooks

## 2026-08-21
* **ingest_source**: 导入外部文档: tam-team-memory-practice (md)
* **ingest_note**: 添加笔记: 下一期方向：资产置信分层与负反馈闭环（Roadmap Phase 5）

## 2026-08-19
* **ingest_note**: 添加笔记: L0 对话归档采用链接优先、零索引设计

## 2026-08-18
* **write_doc_file**: 创建 IDE-Hook采集链路方法.md
* **write_doc_file**: 创建 对话蒸馏管线与raw暂存区.md
* **write_doc_file**: 创建 任务记忆系统设计方法.md
* **write_doc_file**: 创建 MCP-Server薄壳架构与参数约定.md
* **write_doc_file**: 创建 Wiki页面生成约定与数据结构.md

## 2026-08-16
* **ingest_note**: 添加笔记: 技术文章面向业务读者时应削减实现细节、增补业务梳理与开发思路

## 2026-08-15
* **ingest_note**: 添加笔记: ontology.yaml 的 types/relations 是未实现的 schema 骨架，只有 terms 被消费
* **ingest_note**: 添加笔记: PowerShell 下中文经命令行传参（git commit -m / python -c）会被 GBK 破坏，应改用 UTF-8 文件方式
* **ingest_note**: 添加笔记: CodeWiki frontmatter 修补是 additive-only：LLM 直写的 status: draft 不会被默认 stable 覆盖
* **ingest_note**: 添加笔记: 生成的 wiki 页面 status 为 draft 的根因排查：prompt 模板示例会误导 LLM
* **ingest_note**: 添加笔记: wiki 页出现 \x00PROTxxxx\x00 占位符残留会使文件被判为 binary 无法读取
* **ingest_note**: 添加笔记: OKF v0.2 §7 actor 格式：agent 应写 <producer>/<version>，agent: 前缀不在规范内，消费端仅凭 human: 前缀推导信任档位
* **ingest_note**: 添加笔记: YAML frontmatter 裸 f-string 插值 Windows 路径产生非法转义 \c 导致整个 frontmatter 无法解析（OKF §11 违规），字符串字段一律用 json.dumps 转义
* **ingest_note**: 添加笔记: 私有键统一折叠进 metadata:（单行 JSON 值）形成闭环，防止全量生成恢复顶层键
* **ingest_note**: 添加笔记: query_wiki 索引机制：frontmatter 除 6 个 boost 字段外一律剥离不进 BM25，metadata 折叠与 json.dumps 转义不影响检索
* **ingest_note**: 添加笔记: migrate_okf --fold-private 改行手术折叠避免跨行 flow 值 churn；新增 repair_double_quoted_escapes 先修复坏转义再折叠
* **ingest_note**: 添加笔记: wiki_lint 需豁免 raw/ 根暂存层但保留 raw/sources/，RAW_DIR 须单独处理不可塞进 _scratch_dirs
* **ingest_note**: 添加笔记: IDE hook 的 SessionEnd envelope 须用 user 角色，system 角色会被 transcript 提取丢弃
* **ingest_note**: 添加笔记: 任务记忆采用单一 memories.md 追加式原子写，非每次新建文件
* **ingest_note**: 添加笔记: 任务归属在采集阶段决定，蒸馏仅读回 task_id 不做推断
* **ingest_note**: 添加笔记: capture_conversation 的 task_id 需显式传入，绑定文件曾不被自动消费（已加回退修复）
* **ingest_note**: 添加笔记: task_bindings 只与任务存在性挂钩，不校验活跃/完成状态
* **ingest_note**: 添加笔记: 任务记忆蒸馏改为 pending 暂存 + 确认闸门，与笔记评审对齐
* **ingest_note**: 添加笔记: _process_llm_output 是蒸馏三种模式的共同落盘路径，改一处全覆盖
* **ingest_note**: 添加笔记: MCP server 层架构摩擦点扫描结论（7 项，按严重度排序）
* **ingest_note**: 添加笔记: output_dir 解析收敛方案：resolve_workspace 单点 + 优先级统一
* **ingest_note**: 添加笔记: MCP server 薄壳化架构：server.py 职责拆分到 registry/prompts/resources/tools
* **ingest_note**: 添加笔记: module_tree.json 的 children 是字符串引用而非嵌套对象
* **ingest_note**: 添加笔记: get_prompt 工具参数是 prompt_type 而非 name
* **ingest_note**: 添加笔记: 蒸馏多文件时逐文件处理 + 每文件后触发上下文压缩，避免累积撑满
* **ingest_note**: 添加笔记: write_doc_file 默认 status=stable，与笔记/蒸馏的 draft 语义分层
* **ingest_note**: 添加笔记: OKF §7 actor 约定是 codewiki/<version>，旧格式 agent:codewiki/ 已废弃
* **ingest_note**: 添加笔记: no_knowledge 的 raw 由 distill 清理删除，keep_raw 是唯一保留途径
* **ingest_note**: 添加笔记: 任务记忆系统 grill 决策：绑定按 source_session_id 维度，注入走起 session 引导而非 hook 自动注入
* **ingest_note**: 添加笔记: CodeBuddy hook 有源/项目双副本，改 task_session_start.py 需同步源副本才随包分发
* **ingest_note**: 添加笔记: hook 注入的 additionalContext 是软约束，需硬性执行顺序 + 直接注入任务标题才可靠

## 2026-08-13
* **lint_wiki**: 检查完成: 53 个问题
* **lint_wiki**: 检查完成: 53 个问题
* **lint_wiki**: 检查完成: 53 个问题

## 2026-08-12
* **ingest_note**: 添加笔记: IDE hook 采用「同步采集 + 异步蒸馏」两段式执行模型
* **ingest_note**: 添加笔记: repowiki/raw/ 目录堆积会使同步捕获线性变慢，逼近 60s 超时
* **ingest_note**: 添加笔记: TencentDB-Agent-Memory 四层记忆金字塔：逐层蒸馏 + 触发式调度
* **ingest_note**: 添加笔记: query_wiki 的 output_dir 非必填，解析顺序为 output_dir → session → repo_path
* **ingest_note**: 添加笔记: MCP 工具无法自动探测当前项目路径，需显式传 repo_path
* **ingest_note**: 添加笔记: resolve_session 恢复的 session.output_dir 会覆盖 repo_path 推断，导致 Note not found
* **ingest_note**: 添加笔记: confirm_note/reject_note 的 output_dir 解析顺序改为 output_dir → repo_path → session
* **ingest_note**: 添加笔记: CodeBuddy IDE 把系统上下文注入 user 消息，采集时必须剥离系统标签块
* **ingest_note**: 添加笔记: 块剥离正则不要用 ^ 行首锚点：系统块前可能有 user: 前缀
* **analyze_repo**: 分析仓库 CodeWiki-CN，1311 个组件

## 2026-08-09
* **ingest_note**: 添加笔记: CodeBuddy index.json transcript 是裸 JSON 数组，_load_transcript 必须支持 list 顶层展开
* **ingest_note**: 添加笔记: Windows 下 hook 按 sys.stdin.read() 读取中文事件会崩溃，必须按字节读 + 显式 UTF-8 解码
* **ingest_note**: 添加笔记: 同一会话的 PreCompact/Stop 不带 transcript_path，落空信封会被 duplicate 去重，应视为 no-op
* **ingest_note**: 添加笔记: hook 事件信封合成时须置空 source_session_id，否则 supersede 会覆盖真实 transcript（数据丢失）
* **ingest_note**: 添加笔记: 归档对话文件名用用户首句 slug，且与 conversation_id 必须一致（蒸馏链路依赖此约束）
* **ingest_note**: 添加笔记: 无知识的 raw 对话蒸馏后也应清理，删除条件要用 produced is not None 而非 truthy

## 2026-08-08
* **capture_conversation**: 采集对话: conv-20260808T081955Z.md (2 turns, link_to=-)
* **ingest_note**: 添加笔记: CodeBuddy IDE transcript_path 指向的 index.json 只存元数据，真实内容在 messages/<id>.json

## 2026-08-06
* **capture_conversation**: 采集对话: conv-20260806T013027Z.md (2 turns, link_to=-)

## 2026-08-05
* **capture_conversation**: 采集对话: conv-20260805T075743Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T103603Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T104343Z.md (2 turns, link_to=-)
* **capture_conversation**: 采集对话: conv-20260805T104547Z.md (2 turns, link_to=-)

## 2026-08-03
* **lint_wiki**: 检查完成: 27 个问题

<!-- 以下为 v5.1.x 旧格式日志存档 -->
| 时间 | 操作 | 说明 |
|------|------|------|
| 2026-07-28T11:52:32+08:00 | analyze_repo | 分析仓库 CodeWiki-CN，528 个组件 |
| 2026-07-28T11:57:00+08:00 | write_doc_file | 创建 /Users/kirito/repos/CodeWiki-CN/repowiki/wiki/modules/CLI_Adapter.md |
| 2026-07-28T18:00:00+08:00 | write_doc_file (批量) | 生成其余 25 个模块文档：CLI / CLI_Commands / CLI_Config / CLI_Utils / DependencyAnalyzer / AnalysisPipeline / AnalyzerModels / AnalyzerUtils / GraphAndSort / LanguageAnalyzers / RouteExtractors / Frontend / DocVisualizer / WebApp / LLM_Backend / SharedConfig / MCP_Server / MCP_Cache / MCP_Core / MCP_Prompts / MCP_Tools_Analysis / MCP_Tools_Dependency / MCP_Tools_DocWriter / MCP_Tools_Knowledge / MCP_Tools_Quality |
| 2026-07-28T18:00:00+08:00 | rebuild_index | 重建 index.md（26 个模块文档索引）与 overview.md（仓库架构总览） |
| 2026-07-28T12:49:03+08:00 | close_session | 会话关闭 |
| 2026-07-28T13:06:32+08:00 | analyze_repo | 分析仓库 CodeWiki-CN，528 个组件 |
| 2026-07-28T13:09:33+08:00 | write_doc_file | 创建 mcp_smoke_test.md |
| 2026-07-28T13:09:36+08:00 | ingest_source | 导入外部文档: mcp_smoke_src_a (md) |
| 2026-07-28T13:09:37+08:00 | ingest_note | 添加笔记: MCP_TEST_BATCH_NOTE |
| 2026-07-28T13:09:37+08:00 | ingest_source | 导入外部文档: mcp_smoke_src_b (md) |
| 2026-07-28T13:09:38+08:00 | batch_ingest | 批量导入完成: 2 成功, 0 失败 |
| 2026-07-28T13:09:40+08:00 | ingest_note | 添加笔记: MCP_TEST_SMOKE_NOTE |
| 2026-07-28T13:09:51+08:00 | flag_issue | 新增问题: [orphan_page] wiki/queries/mcp_smoke_test.md |
| 2026-07-28T13:10:09+08:00 | retract_source | 撤回外部文档: mcp_smoke_src_a (mode=remove_refs) |
| 2026-07-28T13:10:10+08:00 | retract_source | 撤回外部文档: mcp_smoke_src_b (mode=remove_refs) |
| 2026-07-28T13:11:07+08:00 | write_doc_file | 创建 mcp_smoke_test.md |
| 2026-07-28T13:11:42+08:00 | edit_doc_file | 更新 mcp_smoke_test.md (str_replace) |
| 2026-07-28T13:12:40+08:00 | close_session | 会话关闭 |
| 2026-07-28T13:12:44+08:00 | lint_wiki | 检查完成: 80 个问题 |
| 2026-07-28T13:42:56+08:00 | lint_wiki | 检查完成: 1 个问题 |
| 2026-07-28T13:43:30+08:00 | edit_doc_file | 更新 _tmp_edit_test.md (str_replace) |
| 2026-07-28T13:43:31+08:00 | edit_doc_file | 更新 _tmp_edit_test.md (str_replace) |
| 2026-07-28T13:48:25+08:00 | flag_issue | 新增问题: [broken_link] wiki/modules/X.md |
| 2026-07-28T13:48:25+08:00 | flag_issue | 新增问题: [custom] p |
| 2026-07-28T14:09:25+08:00 | lint_wiki | 检查完成: 3 个问题 |
| 2026-07-28T14:09:26+08:00 | flag_issue | 新增问题: [custom] wiki/modules/_retest.md |
| 2026-07-28T14:10:00+08:00 | lint_wiki | 检查完成: 1 个问题 |
| 2026-07-28T14:10:06+08:00 | edit_doc_file | 更新 MCP_Cache.md (str_replace) |
| 2026-07-28T14:10:22+08:00 | edit_doc_file | 撤销 MCP_Cache.md |
| 2026-07-28T14:11:28+08:00 | close_session | 会话关闭 |
| 2026-07-28T14:11:33+08:00 | lint_wiki | 检查完成: 1 个问题 |
* **lint_wiki**: 检查完成: 27 个问题
* **ingest_note**: 添加笔记: MCP 工具 schema 不声明 session_id，handler 隐式读取
* **ingest_note**: 添加笔记: Entity/Concept 提取采用 WeKnora 式两阶段流程（P0：纯 prompt 协议）
* **ingest_source**: 导入外部文档: README_CN (md)
* **write_doc_file**: 创建 README_CN.md
* **write_doc_file**: 创建 WeKnora.md
* **write_doc_file**: 创建 Langfuse.md
* **write_doc_file**: 创建 微信对话开放平台.md
* **write_doc_file**: 创建 ClawHubSkill.md
* **write_doc_file**: 创建 RAG.md
* **write_doc_file**: 创建 ReActAgent.md
* **write_doc_file**: 创建 Wiki模式.md
* **write_doc_file**: 创建 文档知识图谱.md
* **write_doc_file**: 创建 空间RBAC.md
* **write_doc_file**: 创建 混合检索策略.md
* **close_session**: 会话关闭
* **close_session**: 会话关闭
* **close_session**: 会话关闭
* **analyze_repo**: 分析仓库 CodeWiki-CN，1248 个组件
* **ingest_note**: 添加笔记: 检索引擎架构说明
* **close_session**: 会话关闭
