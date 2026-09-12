### 2026-09-11 08:58

### 2026-09-11（来自「他山之石」整体调研的转交）

codebase-memory-mcp 新增能力里有一项与本任务同层，转你裁决：workspace 边界 + manifest 审批（commit 03e93557 / 80d52797）——workspace.c:186 classify_root 按广度/敏感度分类索引根；:583 manifest_read 读项目级 manifest；:673 manifest_is_approved 用**内容摘要**做审批键（:603 注释：manifest 变了审批即失效）。解决的是「多仓授权 + 改了要重批」。

本仓现状：codewiki/mcp/tools/workspace_bootstrap.py 里没有 approve/manifest/trust 一类的授权概念（grep 0 命中），多仓是「知识归属」维度。

判定提示（不替你拍板）：related ≠ same——他们的 project 是**授权/分发**维度，我们是**归属**维度，与 teamai #375 当时被 excluded 的理由同类（分发 vs 归属）。若要采纳，需先回答「本仓多仓场景下谁有权批准、批什么」；若答不出，直接 excluded 并写明原因。

来源：docs/借鉴项目整体增量调研报告-2026-09.md §2 第 10 项。

### 2026-09-12 08:56

### 2026-09-12

转注撤回：2026-09-11 整体增量调研报告（docs/借鉴项目整体增量调研报告-2026-09.md）deferred #10「CBM workspace manifest 审批键 → 转多仓工作区」系误读，作废。核实结论：CBM（codebase-memory-mcp）的 workspace manifest 实为 **Rust Cargo.toml workspace 清单**，用于跨 crate 导入解析（src/pipeline/pass_lsp_cross.c:478-488），与多仓审批/manifest 无关。实施多仓工作区时勿再消费该参考。详见 repowiki/wiki/queries/参考项目记忆存储与压缩机制对比-2026-09.md。
