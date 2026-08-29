### 2026-08-29 06:32

remove_workspace_repo 移除 delete_dir 参数：注销登记后无条件删除本地 clone 目录（用户要求移除即视为同意删除，不再单独确认）。新增 _rmtree_clear_readonly（onexc）处理 Windows 只读文件。同步更新：registry schema、prompts（删确认步骤与参数）、resources 目录、README 中英文、docs 管理模型文档、test_workspace_bootstrap / test_remove_repo_cleanup。验证：42/42 相关测试过；全量 563 过（2 个既有环境性失败：ruamel 缺失、git 用户 ID 为 local）；ruff 0.16.3 通过。

### 2026-08-29 06:43

init_workspace 移除 refresh_conventions 参数，约定块改为每次强制刷新覆盖（块由工具维护，自定义内容写在标记块外）。write_workspace_conventions 同步删掉 refresh 形参与 "kept" 分支，返回仅 created/refreshed。同步更新：registry schema/描述、prompts（init-workspace 参数与幂等说明）、resources 目录、README 中英文、docs 管理模型文档、test_workspace_bootstrap（TestIdempotency 重写 + schema 断言）、test_workspace_layout（重命名 reinit 用例）。验证：89 相关测试过；全量 563 过（同 2 个既有环境性失败）；ruff 0.16.3 通过。

### 2026-08-29 07:14

init_workspace 重构为零配置同步操作：schema 仅保留 output_dir（workspace_path/layout/with_readme 从 schema 移除，handler 宽容接受供测试与首次集中式初始化使用）；重跑自动沿用已持久化布局（无参重跑不再报冲突，显式传矛盾值才报错）；新增自动 clone：遍历登记表克隆未克隆的业务仓（失败仅警告，集中式新克隆同步移除仓内 CodeWiki 块），克隆超时固定 600s；README 缺失即建。同步更新 prompts/resources/README 中英文/管理模型文档。测试：新增 TestInitAutoClone×5 + 布局 adopt 用例，重写 schema/冲突/prompt 渲染用例；全量 573 过（同 2 个环境性失败）；ruff 通过（顺手修了并发会话引入的 E741）。真机验证：恢复 harness 登记后零参运行，codewiki-plus 自动克隆成功，二次重跑 skipped 幂等。

### 2026-08-29 07:18

修复 remove_workspace_repo 不清理 analyze_workspace 持久产物的问题（用户在 harness 工作区发现移除业务仓后 workspace_routes.json 残留幽灵路由）。新增 _cleanup_analysis_artifacts：workspace_routes.json 按 repo_name 过滤、cross_service_links.json 按 client_repo/server_repo 过滤、infra_services.json 按 source_path 前缀过滤（无该字段的旧缓存条目保留不判）、生成的 overview.md 删除该仓服务行/链接/归属 infra 行；两种布局均执行（产物是工作区级可再生缓存，非知识）。InfraServiceInfo 新增 source_path（compose 文件相对工作区的 POSIX 路径——相对路径在工作区搬迁后仍可归属）。同步更新：registry 描述、remove prompt 校验步骤、管理模型文档 §4.3（补记 ticket 10 知识清理 + 本次产物清理）、README 中英文。测试：新增 TestRemoveAnalysisArtifacts×4（含 legacy 无归属条目保留、无产物安全路径、colocated 同清）。验证：受影响文件 100 过、全量 573 过（同 2 个环境性失败）、ruff 通过。存量修复：D:\repos\CodeWiki-Plus-Harness 的 routes 置 []、infra 置 {}、overview 删 codewiki-plus 行（git 可回退）。注意：本会话与另一会话（init_workspace 重构）并发编辑同批文件，已复核己方改动完好。

