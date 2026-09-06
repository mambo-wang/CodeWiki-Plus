# OpenWiki（langchain-ai/openwiki）调研笔记

> 调研对象：本地克隆 `D:\repos\CodeWiki-CN\.research-competitors\openwiki`（TypeScript，v0.5.0）。
> 所有论断均基于源码核对，标注 `文件:行号`（相对仓库根）。

## 1. 整体架构与定位

OpenWiki 是一个 **npm CLI**（`package.json` 的 `bin.openwiki` 指向 `dist/cli/cli.js`，description 为 "A CLI that uses a DeepAgents documentation agent to generate and maintain an OpenWiki for a codebase"），基于 **LangChain/LangGraph + deepagents** 构建，交互 UI 用 Ink（React for CLI）。它同时是三合一：

1. **CLI Agent 工具**：命令解析入口 `src/cli/commands.ts:168`（`parseCommand`），支持 `--init/--update`、`code`/`personal` 双模式（`src/cli/commands.ts:26` 的 `OpenWikiRunMode`）、`ingest`/`cron`/`auth`/`ngrok`/`visualize`/`integrations`/`mcp` 子命令（`src/cli/commands.ts:107-164` 的 `CliCommand` 联合类型）。
2. **MCP server**（内部）：`openwiki mcp --host <id>` 启动一个"rootless"生命周期 MCP 服务器（`src/cli/commands.ts:658` `parseMcpCommand`；`src/integrations/mcp/server.ts:50` `createOpenWikiMcpServer`）。
3. **Agent 库形态的集成**：把自身作为 skill+MCP 安装进 Codex/Claude Code/OpenCode/Cursor 四个宿主（`src/integrations/install/registry.ts:12,32,46,66`）。

核心生成流程入口是 `runNativeRepositoryGeneration`（`src/agent/repository-runner.ts:205`）；聊天/agent 组装在 `src/agent/index.ts:481`（`createDeepAgent`），带 SQLite checkpointer（`src/agent/index.ts:9,811`）。定位 slogan 是"self-maintaining wiki, built for agents, explored by humans"——**wiki 首先写给 Agent 当记忆用**，人类用可视化浏览器（`src/visualize/server.ts`）阅读。

## 2. 代码分析阶段

**完全没有 AST/tree-sitter/ctags/依赖图提取，也没有嵌入向量**（对 src/ 全文 grep `embedding|vector|rag` 仅命中无关文案）。分析 = LLM agent 直接用文件系统工具读代码：

- 工具集：planner 只有只读 `read_file/ls/glob/grep`（`src/agent/repository-runner.ts:74` `PLANNER_FILESYSTEM_TOOLS`）；page worker 加上 `write_file/edit_file`（`src/agent/repository-runner.ts:75-79`），外加 `submit_plan/inspect_claims/submit_page` 三个生命周期工具（`src/agent/repository-runner.ts:80-85`）。
- 文件系统是**虚拟根沙箱**：`OpenWikiLocalShellBackend`（`src/agent/docs-only-backend.ts:166`）把 `/` 映射到目标仓库，docsOnly 模式下写权限被限制在 `writableWikiPages` 白名单（每页 worker 只能写自己那一页，`src/agent/docs-only-backend.ts:517-527`；`src/agent/repository-runner.ts:415-424` 传入 `[job.path]`）；shell `execute` 在 `.openwikiignore` 激活时被整体禁用（`src/agent/docs-only-backend.ts:487-508`），且永远禁止触碰 Claims 内部状态。
- 依赖结构不显式提取。planner prompt 要求按"owned systems, runtime domains, cross-system workflows"组织信息架构而非镜像目录树（`src/agent/repository-prompts.ts:49-54`），探索策略是"先看 manifests/入口/公共面 → 追端到端流 → 看测试"（`src/agent/repository-prompts.ts:57-64`）。发现类指令偏好 `rg --files` 加排除目录（`src/agent/prompt.ts:161`），允许读 git 历史建立上下文（`src/agent/prompt.ts:152-156`）。

## 3. 文档生成流程

**明确两阶段**：planner（结构）→ 逐页 worker（内容），且全程持久化可恢复：

- **Planning**：一个有界 planner agent 只能输出 `submit_plan`，plan schema 为 `pages[]{path,title,purpose,seedPaths,relatedPages,instructions}` + `deletePages`（`src/agent/repository-runner.ts:38-54`）；init 必须含 `/openwiki/quickstart.md`，update 禁止删它（`src/agent/repository-prompts.ts:72-75`）。禁止子代理委派（`src/agent/repository-runner.ts:90-97` `NO_DELEGATION_MIDDLEWARE` 过滤掉 deepagents 注入的 task 工具）。
- **逐页生成**：持久化有序队列，`nextRepositoryPage` 顺序取页（`src/agent/repository-runner.ts:373-397`），每页一个全新 agent（`runPageAgent`，`src/agent/repository-runner.ts:407`），prompt 含该页 purpose/seedPaths/relatedPages + 待决策的 Claims 清单（`src/agent/repository-prompts.ts:114-178`）。提交校验失败会以"可纠正的 tool 错误"回给 worker 重试（`src/agent/repository-runner.ts:113-134` `createSubmissionRejection`）；worker 崩溃则恢复页快照并跳过、留待下次 update（`src/agent/repository-runner.ts:505-517`）。
- **确定性收尾**（非 LLM）：mermaid 校验→索引同步→内链校验→Claims sources 投影→generated provenance 盖章（`src/agent/wiki-finalizer.ts:248-285` `finalizeWikiArtifacts`）。目录 `index.md` 由代码确定性生成，禁止模型手写（`src/agent/prompts/code.ts:31`）。坏链不打断流程，原地标记 HTML 注释供下次自愈（`src/agent/prompt.ts:133-139`）；mermaid 解析失败降级为 text fence 并留修复注释（`src/agent/prompt.ts:141-149`）。
- **Prompt 策略亮点**：OKF v0.2（Google Knowledge Catalog 开放知识格式）frontmatter 强制要求 `type/title/description/tags`，description 明确"optimized for search & retrieval"（`src/agent/prompts/code.ts:63-88`）；mermaid 图谱纪律按图型分类（sequenceDiagram/stateDiagram/erDiagram/flowchart，`src/agent/prompt.ts:141-149`）；秘密文件（.env 等）禁读（`src/agent/prompts/code.ts:56-61`）。
- **增量更新机制（最重的工程设计）**，多层：
  1. **no-op 检测**：对比 `.last-update.json` 记录的 gitHead 与当前 HEAD/worktree status，只有 openwiki 自身路径变化则跳过（`src/agent/utils.ts:126-195` `getUpdateNoopStatus`）；
  2. **源指纹**：sha256 哈希全部 tracked+untracked 文件内容与 porcelain status（`src/agent/utils.ts:331-404` `createRepositorySourceSnapshot`），运行中源漂移会不推进 checkpoint、提示用户再 update（`src/agent/repository-runner.ts:244-253`）；
  3. **每页源 checkpoint**：`openwiki/.page-manifest.json` 记录每页覆盖的指纹（`src/generation/page-manifest.ts:35` `RepositoryPageManifestEntry`），update 时未受影响页直接 fast-forward（`src/generation/repository-run.ts:391` `fastForwardUnchangedRepositoryPageCoverage`）；
  4. **页级 update window**：按页的已提交 git baseline 分组，连同 changedPaths 喂给 planner 决定哪些页真正需要重写（`src/agent/repository-prompts.ts:215-231` `formatPageUpdateWindows`；`src/generation/repository-run.ts:145-167` 类型定义）；
  5. **Grounded Claims**：每页的实质事实命题以 sidecar JSON 存于 `openwiki/.claims`（`src/claims/brains/code/store.ts:84,116`），证据 URI 为 `repo://<path>#L20-L48` 且带内容哈希版本；update 前 preflight 逐条比对证据版本，产出 stale/unresolved 清单（`src/claims/brains/code/preflight.ts:36-96`）。证据版本编码了行范围"重定位锚点"（首/末行哈希+上下文哈希），行号漂移后能自动重锚（`src/claims/evidence/repository/resolver.ts:22-69`）。worker 提交稀疏 reconciliation（confirm/revise/retract），无争议 Claims 自动保留（`src/claims/guidance.ts:18-24`）。
- **init 安全性**：重新 init 会把旧 wiki 备份到临时目录，失败/ SIGINT/SIGTERM 均回滚，只保留用户手写的 `INSTRUCTIONS.md`（`src/agent/wiki-replacement.ts:42-80`）。运行状态持久化在 `openwiki/.run.json`，中断后 resume（`src/generation/run-state.ts`）。
- **多语言**：`--language` 切换时先跑一轮确定性翻译 pass 把存量页面翻到目标语言，模型只写新增内容（`src/agent/translation-middleware.ts:187` `translateWiki`；`src/agent/prompt.ts:123-130`）。

## 4. 检索/问答能力

**无 RAG/嵌入/混合检索**（grep 证实）。问答链路是"agent + 文件系统工具"：

- code 模式聊天 prompt 明确要求 **wiki-first QA**："inspect the generated wiki under /openwiki first"，先 grep/glob wiki 再看源码，用户问"wiki 怎么说"时只用 wiki 页面（`src/agent/prompts/code.ts:25-28`）。
- 聊天会话经 SQLite checkpointer 持久化（`src/agent/index.ts:416-422,811`），并有 checkpoint 裁剪防膨胀（`src/agent/index.ts:837-897`）。
- **没有 web UI 问答**。`openwiki visualize` 只是只读的节点图 + Markdown 阅读器本地服务/静态导出（`src/cli/commands.ts:305-402`；`src/visualize/`）。OKF frontmatter 的 description 字段是为"外部检索工具"预留的接口，自身未实现检索。
- personal 模式有 9 类连接器摄取（`src/connectors/sources/`：mcp、slack、gmail、x、web-search、hackernews、langsmith、git-repo），`openwiki ingest` 触发（`src/cli/commands.ts:404-486`），但这是个人知识库方向，与代码 wiki 主线正交。

## 5. MCP / Agent 集成

- **MCP server**：`openwiki mcp` 暴露 6 个生命周期工具 `openwiki_begin / submit_plan / next_page / inspect_page_claims / submit_page / finish`（`src/integrations/mcp/server.ts:11-30` 的 INSTRUCTIONS），本质是把第 3 节的持久化队列开放给外部宿主——宿主 coding agent（用自己的模型和原生仓库工具）做研究和写页，OpenWiki 管队列、校验、Claims、收尾（`integrations/openwiki/SKILL.md:8-65` 详述契约）。
- **`skills/` 目录**：随包分发的 deepagents 技能（`mermaid-diagrams`、`write-connector`），安装时原子同步到 `~/.openwiki`（`src/agent/skills.ts:24-118`，含读-only Nix 场景的权限自愈），运行时以 `skills: ["/skills/"]` 注入 agent（`src/agent/repository-runner.ts:348,484`）。
- **宿主集成**：`openwiki integrations install codex|claude|opencode|cursor` 安装 SKILL.md+MCP 配置（user 级或 `--project` 仓库级），支持 list/uninstall（`src/cli/commands.ts:539-650`；`src/integrations/install/registry.ts`）。

## 6. 值得注意的工程设计

- **可恢复页作业生命周期**：`begin → submit_plan → next_page → submit_page → finish`，每页推进前 Markdown+Claims+manifest 均落盘；CI（GitHub Actions/GitLab/Bitbucket 定时 workflow，由 `ensureCodeModeRepoSetup` 自动生成 `.github/workflows/openwiki-update.yml`，`src/ingestion/code-mode.ts:65-93`）跑挂后重跑即续。
- **Claims 账本 + 证据版本重锚**（见第 3 节）：把"文档是否过时"从模糊判断变成可机械验证的状态机，这是与 DeepWiki 类产品拉开差距的核心。
- **eval 体系非常重**：LEDGER（`evals/ledger/`）——回放 git checkpoint、逐条抽取 wiki 原子事实命题、判定 supported/stale/invented(hallucinated)/unverified 四态等分母分区（`evals/ledger/README.md`），带 BM25 语义 evidence map 路由、金标准一致性 ≥0.90 的 judge 元评估门槛（`evals/ledger/meta/README.md`）；另有 DeepSWE 配对实验验证"有 wiki 的 Codex 是否更能修 bug"（`evals/deepswe/README.md`）。
- **成本/一致性取舍**：页队列**严格串行**（`while(true) nextRepositoryPage`，`src/agent/repository-runner.ts:380-396`），无并行页生成；planner/page worker 均禁止委派子代理。
- 其他：细粒度 telemetry（仅 init/update 发一条 `openwiki_run` 事件，`src/cli/commands.ts:1062-1068`）；技能目录原子安装处理 Windows EPERM/并发竞争（`src/agent/skills.ts:53-118`）；Windows ACL 处理（`src/platform/windows-acl.ts`）。

## 7. 明显短板/局限

1. **无检索层**：问答靠 agent 拿 grep/glob 翻 wiki 文件，wiki 大了以后命中率和 token 成本都会退化；OKF description 字段是"留给别人做检索"的空位。
2. **无静态分析**：不建 AST/调用图/依赖图，结构质量完全取决于 planner 模型的判断；跨页一致性只靠 plan 里的 relatedPages 和 quickstart 路由，无机械校验（除内链外）。
3. **串行逐页生成**：大仓库一次 init 可能几十个 page job 顺序跑，时长和费用高，且没有页级并行。
4. **worker 失败静默降级**：页 worker 崩溃只回滚快照并跳过（`src/agent/repository-runner.ts:505-517`），一次 run 可能留下不完整 wiki，要等下一轮 update 补。
5. **状态文件入侵仓库**：`openwiki/.run.json`、`.claims/`、`.page-manifest.json`、`.last-update.json` 全部进 git；强 git 依赖（无 git 的目录指纹走 unborn 分支特殊路径）。
6. **personal 模式 cron 偏 macOS**（launchd 语义，`src/cli/commands.ts:1151-1167` 帮助文本）；交互聊天需 TTY，非 TTY 只能 `--print` 单轮（`src/cli/commands.ts:1040-1049`）。
7. **无 web 问答服务**：visualizer 是只读阅读器，对比 DeepWiki 的"网页问答"形态是明显缺位。

## 一句话总结

OpenWiki 的差异化不在"生成 wiki"本身，而在**工程化的事实治理**：两阶段 plan→逐页生成、持久化可恢复队列、git 基线 + 源指纹 + 页级 checkpoint 的多层增量、带证据版本重锚的 Grounded Claims、OKF 标准化输出，以及 LEDGER 纵向漂移 eval——但检索/问答和静态分析层面几乎空白，问答完全靠 agent 翻文件。
