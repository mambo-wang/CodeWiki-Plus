### 2026-08-29 06:32

remove_workspace_repo 移除 delete_dir 参数：注销登记后无条件删除本地 clone 目录（用户要求移除即视为同意删除，不再单独确认）。新增 _rmtree_clear_readonly（onexc）处理 Windows 只读文件。同步更新：registry schema、prompts（删确认步骤与参数）、resources 目录、README 中英文、docs 管理模型文档、test_workspace_bootstrap / test_remove_repo_cleanup。验证：42/42 相关测试过；全量 563 过（2 个既有环境性失败：ruamel 缺失、git 用户 ID 为 local）；ruff 0.16.3 通过。

### 2026-08-29 06:43

init_workspace 移除 refresh_conventions 参数，约定块改为每次强制刷新覆盖（块由工具维护，自定义内容写在标记块外）。write_workspace_conventions 同步删掉 refresh 形参与 "kept" 分支，返回仅 created/refreshed。同步更新：registry schema/描述、prompts（init-workspace 参数与幂等说明）、resources 目录、README 中英文、docs 管理模型文档、test_workspace_bootstrap（TestIdempotency 重写 + schema 断言）、test_workspace_layout（重命名 reinit 用例）。验证：89 相关测试过；全量 563 过（同 2 个既有环境性失败）；ruff 0.16.3 通过。

### 2026-08-29 07:14

init_workspace 重构为零配置同步操作：schema 仅保留 output_dir（workspace_path/layout/with_readme 从 schema 移除，handler 宽容接受供测试与首次集中式初始化使用）；重跑自动沿用已持久化布局（无参重跑不再报冲突，显式传矛盾值才报错）；新增自动 clone：遍历登记表克隆未克隆的业务仓（失败仅警告，集中式新克隆同步移除仓内 CodeWiki 块），克隆超时固定 600s；README 缺失即建。同步更新 prompts/resources/README 中英文/管理模型文档。测试：新增 TestInitAutoClone×5 + 布局 adopt 用例，重写 schema/冲突/prompt 渲染用例；全量 573 过（同 2 个环境性失败）；ruff 通过（顺手修了并发会话引入的 E741）。真机验证：恢复 harness 登记后零参运行，codewiki-plus 自动克隆成功，二次重跑 skipped 幂等。

### 2026-08-29 07:18

修复 remove_workspace_repo 不清理 analyze_workspace 持久产物的问题（用户在 harness 工作区发现移除业务仓后 workspace_routes.json 残留幽灵路由）。新增 _cleanup_analysis_artifacts：workspace_routes.json 按 repo_name 过滤、cross_service_links.json 按 client_repo/server_repo 过滤、infra_services.json 按 source_path 前缀过滤（无该字段的旧缓存条目保留不判）、生成的 overview.md 删除该仓服务行/链接/归属 infra 行；两种布局均执行（产物是工作区级可再生缓存，非知识）。InfraServiceInfo 新增 source_path（compose 文件相对工作区的 POSIX 路径——相对路径在工作区搬迁后仍可归属）。同步更新：registry 描述、remove prompt 校验步骤、管理模型文档 §4.3（补记 ticket 10 知识清理 + 本次产物清理）、README 中英文。测试：新增 TestRemoveAnalysisArtifacts×4（含 legacy 无归属条目保留、无产物安全路径、colocated 同清）。验证：受影响文件 100 过、全量 573 过（同 2 个环境性失败）、ruff 通过。存量修复：D:\repos\CodeWiki-Plus-Harness 的 routes 置 []、infra 置 {}、overview 删 codewiki-plus 行（git 可回退）。注意：本会话与另一会话（init_workspace 重构）并发编辑同批文件，已复核己方改动完好。

### 2026-08-29 17:28

init_workspace clone-only 接管已实现并被并发提交吸收（f337429）：痕迹齐备（bootstrap 双脚本+可解析登记表+.gitignore+repowiki/wiki+schema.yaml）重跑只补克隆+修 gitignore 排除行，不碰骨架/AGENTS.md；痕迹缺失走完整同步修复。返回 mode/mode_reason/traces；handler 拆 _detect_init_traces/_adopt_initialized_workspace/_run_full_skeleton_flow。用户修正：痕迹齐备时 prompt 指示 agent 直接跑 bootstrap 脚本补克隆、不调 init_workspace（clone-only 是误调兜底）。

并发会话后续：af643e2 加首次初始化布局闸门+workspace.json 两布局总写入（对应用户 go-my-harness「没问模式」抱怨），与 clone-only 集成、测试已适配；b792349 改 centralized 分析缓存位置（成员仓保持纯代码），遗留过期断言 test_generate_repo_wikis_populates_analysis 红——归属该会话，未代修。

Wiki 增量更新设计定稿归档 docs/多仓Harness工作区-Wiki增量更新设计方案.md：三档分派（未变更仓跳过=HEAD vs metadata commit_id+worktree 干净/变更仓增量=重跑 analyze_repo+affected_modules 清单/无 wiki 全量）；锚点复用 metadata.json generation_info.commit_id 不新造；改写复用 incremental-update prompt；唯一新缝=centralized 缓存按仓命名空间 .meta/<仓名>/（metadata/module_tree/changes）；非目标：A2 watch 单次增量同步、force/repos 参数、analyze_changes 驱动。待排期实现。

验证：受影响 98 过+ruff 过；全量 587 过（2 环境性失败+1 并发会话归属红测试）。

### 2026-08-29 18:38

Wiki 增量更新按设计文档实施完成：
- cache.py 新缝 analysis_meta_dir/resolve_analysis_meta_file：colocated→output_dir/.meta 不变；centralized 成员仓→<ws>/.codewiki/<仓名>/（与 b792349 的 SQLite/会话工作区命名空间合一）；旧单文件回退读，归属错配下游安全退化。
- 写读点切换：close_session _write_metadata_json+docs_generated 检查；analysis.py 7c（无锚点则建基线 commit_id=HEAD）+schema 读 module_tree+_detect_doc_changes；module_tree.py save/get 透传 repo_path。
- workspace_analyzer 三档分派+deferred：_read_anchor_commit/_probe_repo_state（untracked 噪音过滤排除仓内 repowiki/ 与 .codewiki/，同 _detect_git_from_meta 哲学——否则 colocated 未提交 wiki 永远脏、永不跳过）；skipped 复用 summary.json stats；incremental/full 透传 changes；拓扑天然复用各仓 SQLite routes。
- 测试 TestIncrementalDispatch×5 + 修 b792349 过期断言（.codewiki/<repo>/analysis_cache.db）。
- 文案：registry 描述、README 中英、管理模型 §5 步 8+§6、设计文档 §3 deferred 档/§4 实现命名空间回写。
- 坑：_save_and_compute_order result 嵌 Path 致 JSON 序列化败（meta_join 原返回 str），str() 修。
- 验证：ruff 过；全量 593 过（仅 2 已知环境性失败）。
