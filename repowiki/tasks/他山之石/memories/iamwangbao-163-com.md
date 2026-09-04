### 2026-09-04 12:12

完成 caveman（JuliusBrussee/caveman）仓库的技能生效机制研究：结论为多宿主分发提示词注入系统——SKILL.md 单事实源经三条链路注入（Claude Code Plugin hooks / CLI+Proxy 的 Native Pack / 通用 skills 目录）；核心机制是 SessionStart hook 的 stdout 作为隐藏系统上下文注入，compact/resume 触发重注入防压缩漂移。

### 2026-09-04 12:12

研究用的 clone 留在 d:/repos/CodeWiki-CN/.caveman-tmp/；对话收尾时向用户提出两个待办选项（整理成 repowiki comparison/query 笔记 or 清理临时目录），尚未收到决定——下一步需确认是否沉淀对比笔记及临时目录去留。

### 2026-09-04 12:23

caveman 研究收尾决定（2026-09-04）：1) 蒸馏草稿①「caveman 技能生效机制」用户拒绝，已 reject_note 标记 deprecated；2) 草稿②「Agent hook 注入的工程化防御与防漂移可复用模式」暂不处理，保留 draft 待定；3) .caveman-tmp/ clone 目录已按用户选择删除清理，无遗留待办。

### 2026-09-04 14:00

「他山之石」caveman 技能生效机制研究已完成（clone 临时目录 d:\repos\CodeWiki-CN\.caveman-tmp\），2 条 architecture 笔记已由用户确认落盘（stable）：2026-09-04-caveman-技能生效机制skillmd-单事实源经三条加载链路注入各-agent-上下文、2026-09-04-agent-hook-注入的工程化防御与防漂移可复用模式caveman-提炼。

### 2026-09-04 14:00

用户询问 CodeBuddy 使用方式后拍板：把 caveman 当普通 Skill「全量」安装到 ~/.codebuddy/skills/（复制 skills/ 下全部纯规则技能，含 caveman-commit/review/help）。安装动作在会话末尾仍在执行（PowerShell 查找 clone 目录），下一步：确认安装完成、新开会话验证 /caveman 触发与退出词，并清理 .caveman-tmp。

### 2026-09-04 14:00

主会话发现 raw/ 下另有 14 条「未关联任务」pending raw（各带 .lck 空锁，系某次未带 task_id 的 submit 误批处理所致，均未落盘副作用），建议由主 Agent 统一安排归属后再蒸馏；本 worker 未触碰。
