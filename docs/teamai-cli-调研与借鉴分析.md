# teamai-cli 调研与借鉴分析

> 调研日期：2026-08-21
> 调研对象：
> - **Tencent/teamai-cli**（`github.com/Tencent/teamai-cli`，v0.20.0）：TypeScript CLI，"面向 AI 智能体的团队 Harness 分发工具"，npm 公开包 `teamai-cli` + 腾讯内网 tnpm 镜像 `@tencent/teamai-cli` 双发布。GitHub 462 stars / 42 forks，首个版本 2026-03-03，约 5.5 个月发布 48 个版本，迭代非常快。
> - **CodeWiki-CN / CodeWiki-Plus**（本仓库）：Python MCP 服务器，AI IDE 驱动的代码文档生成 + 知识管理引擎。
>
> 资料来源：teamai-cli 仓库完整浅克隆（`src/` 345 个文件、约 8.9 万行 TypeScript）+ README/CHANGELOG/docs/designs/CI 配置逐篇阅读；CodeWiki 侧基于本仓库 README、源码与已有调研文档。所有实现细节均落到源码文件名，不含猜测。

---

## 一、执行摘要（TL;DR）

| 维度 | CodeWiki-CN | teamai-cli |
|------|-------------|-----------|
| 一句话定位 | 单仓代码文档生成 + 知识引擎（文档为中心） | 团队 AI Harness 分发 + 团队经验知识库（团队为中心） |
| 交付形态 | MCP Server（40+ 工具）+ CLI | 纯 CLI + IDE Hooks + 内置 subagent + 规则注入 |
| 技术栈 | Python 3.12+，tree-sitter AST，SQLite | TypeScript，**无 AST 库、无 LLM SDK**（正则提取 + spawn 本机 AI CLI） |
| 代码理解 | tree-sitter 依赖图/调用图，10 语言，方法级增量 | 逐行正则事实提取（6 类 extractor），启发式依赖边，7 语言 |
| 文档产物 | 人读 Wiki（module/entity/concept…），OKF v0.2 frontmatter | `teamwiki/` evidence 页 + 导航页（更偏机器消费）+ graph-index.json |
| 检索 | BM25 + jieba + wikilink 多跳 + authority 权重 + 渐进式阅读 | 自研 BM25 + Intl.Segmenter + 图谱加性 boost + 投票/置信度加权 + depth 预算 |
| 经验沉淀触发 | AGENTS.md 规则自觉 + capture hook（默认关）+ 手动 | **摩擦信号自动评分**（Stop hook 扫 transcript） |
| 评审闸门 | draft → confirm_note → stable（IDE 内工具确认） | harness 资源走 MR 评审；**learnings 直推 master 无闸门**，事后投票淘汰 |
| 生命周期维护 | stale_after 时间窗（类型感知，建设中） | **使用信号驱动**：confidence / hot-cold / prune / promote / quality-update |
| 团队协作 | repowiki 随代码仓库提交，无专门分发机制 | 团队仓 + push/pull + roles/namespace + 跨团队订阅 + user/project scope 分层 |
| 遥测 | retrieval_stats.db（本机、gitignore） | sessions/stats/votes 经孤儿分支共享上报 + digest 周报 + dashboard |
| CI 集成 | 无 | MR 知识提取（comment + merge 后写入）+ teamwiki lint |
| 质量保障 | 16 项 lint + health score + Evidence-Based 断言 | 图谱健康 lint + 检索质量埋点（反哺知识缺口检测） |
| LLM 依赖 | IDE 自身模型（MCP）或自配 API | 全可选：spawn 本机 AI CLI（claude/codex/codebuddy…），确定性链路完全离线 |

**核心结论：**

1. **两者定位互补而非竞争。** CodeWiki 深耕"一个仓库的代码知识"（AST 级理解、文档质量、评审闸门），teamai 深耕"一个团队的 AI 工作方式"（skills/rules/hooks 分发、经验沉淀飞轮、多人协作治理）。teamai 的代码知识图谱（teamwiki）在解析深度上远不如 CodeWiki，但它的**知识飞轮运营机制**（触发、投票、淘汰、晋升、周报）是 CodeWiki 目前缺失的完整一环。

2. **最值得借鉴的不是功能，是"使用信号闭环"。** teamai 把每次检索的命中/采纳/落空都变成数据（recalled/upvoted/recall-miss），这些数据同时驱动四件事：排序加权、冷热淘汰（prune）、晋升正式知识（promote）、质量重写（quality-update）、以及"知识缺口"贡献提示。CodeWiki 已有 `retrieval_stats.db` 热度遥测，但只写不读——把它接进排序和生命周期，是当前新鲜度专项（stale_after）的天然延伸。

3. **"什么时候提示沉淀经验"是 teamai 最精巧的设计。** 摩擦信号评分（用户打断 ×20、拒绝工具 ×20、纠正 ×20、工具失败分档 10/18/25，阈值 20，外加 toolCount≥15 硬门槛）从机制上保证"又长又顺的 session 不触发、真正较劲过的才触发"，且信号全部来自 transcript 客观痕迹而非 LLM 自评。CodeWiki 目前的"纠正识别"完全依赖 AGENTS.md 里的 prompt 自觉，容易漏——这是可直接移植的补强。

4. **teamai 的试错史本身就是一份参考资料。** CHANGELOG 记录了它砍掉被动式 auto-recall PostToolUse hook（噪音大、命中率低、与主动检索重叠），改为任务开始前的 subagent 主动检索；设计文档记录了 SessionStart auto-recall 提案被 subagent 方案取代、Reflect 层因数据不足推迟、贡献者排行榜因团队文化顾虑被明确拒绝。这些"不做什么"的决策对 CodeWiki 规划 hook/检索集成有直接参考价值。

5. **评审闸门是路线分歧，不是优劣。** teamai 的 learnings 直推 master（低摩擦，靠事后投票淘汰），CodeWiki 的 confirm_note 闸门（高质量，靠事前评审）。可考虑折中：按信号强度分级——强摩擦/人工发起的沉淀走快速通道，LLM 自动蒸馏的保持 draft 待确认。

---

## 二、teamai-cli 项目概览

### 2.1 定位：两条主线

teamai 的自我描述是 "The team harness for AI agents"——通过 Git 统一管理 skills、rules、docs，驾驭 Claude Code / Codex / CodeBuddy / WorkBuddy 等多种 AI 工具，"一个人也能用，团队用更强"。实际包含两条主线：

```
主线一：Harness 分发（团队 AI 配置的统一管理）
  团队仓 skills/rules/docs/hooks/mcp.yaml
    → teamai push（建分支 + MR）→ reviewer 合并
    → SessionStart hook 自动 teamai pull
    → 注入到 ~/.claude/、~/.codex/、~/.codebuddy/ 等 28 个 known-agents 目录

主线二：团队知识库（经验沉淀 + 代码图谱 + 检索）
  session 摩擦评分 → /teamai-share-learnings → learnings/ 直推团队仓
  teamai import → teamwiki/ 代码知识图谱
  teamai recall（BM25 + 图谱增强）→ 投票回流 → 置信度维护
```

### 2.2 技术栈与工程约束

依赖清单极简（package.json）：`commander`（CLI）、`simple-git`（git 操作）、`zod`（manifest 校验）、`gray-matter`（frontmatter）、`yaml`、`smol-toml`、`fflate`、`listr2`/`ora`/`chalk`（交互显示）。**没有任何 LLM SDK，没有 tree-sitter 或任何 AST 库**。这决定了两个架构基调：

- LLM 调用一律通过 `utils/ai-client.ts` spawn 本机已登录的 AI CLI（白名单：claude / claude-internal / tclaude / codex / tcodex / codebuddy / workbuddy / openclaw，按序探测），复用各 CLI 自己的登录态——与 CodeWiki"IDE 自身模型驱动"哲学殊途同归，但 teamai 走的是 CLI 子进程而非 MCP。
- 代码解析一律确定性正则（见 3.4），LLM enrich 是可选增强（`--skip-enrich`），保证离线可用。

`CLAUDE.md` 还披露了几条团队工程纪律：CLI 用户可见输出必须全英文（中英双语文档同步维护）、每次改代码必须先进 git worktree、功能必须真实 CLI 端到端验证。发布走 tag 触发双流水线（GitHub Actions 发公开 npm，Coding CI 改名发内网 tnpm）。

### 2.3 两种部署模式

- **独立团队仓模式**：在 Git 平台建共享经验仓库，成员 `teamai init <repo>`；支持 GitHub / TGit（git.woa.com）/ CNB（cnb.cool）三个 provider（`src/providers/`）。
- **单仓模式**（`teamai init .`）：业务仓即团队仓。知识资产（skills/rules/docs/learnings）提交到 main 分支 `.teamai/` 目录（clone 即带上），上报数据（成员注册、会话摘要、投票、统计）走独立的 **`teamai-reports` 孤儿分支**，永不污染 main。所有 git 操作在隔离 worktree 中进行。

单仓模式对 CodeWiki 特别有参考意义——它回答了"团队知识资产放在哪、如何与业务代码共存"的问题（详见 5.2）。

### 2.4 命令地图（README 命令一览 + 源码补充）

| 命令 | 说明 |
|------|------|
| `teamai init` | 初始化：OAuth 登录、关联仓库、注册成员、注入 hooks |
| `teamai pull` / `push` / `status` | 拉取注入 / 推送建 MR / 查看差异 |
| `teamai contribute` | 将 session 经验分享到团队仓（直推 master） |
| `teamai recall <query>` | 检索知识库（BM25 + 图谱增强）；`enable/disable/status` 管理开关 |
| `teamai import` | 导入代码/文档知识（`--from-repo`/`--from-org`/`--from-mr`/`--from-iwiki` 等） |
| `teamai codebase --lint` | 知识图谱健康检查（CI 可用，high 级 exit 1） |
| `teamai ci extract-mr` | CI：从 MR 提取知识、发评论、合并后写入 |
| `teamai session save` / `digest` | 脱敏 session 摘要入月度日志 / 生成团队周报 |
| `teamai members` / `roles` / `source` | 成员 / 角色命名空间 / 跨团队 skill 订阅 |
| `teamai doctor` / `uninstall` | 诊断 / 完整清理 |

---

## 三、关键机制详解

### 3.1 Harness 分发：push → MR 评审 → pull 自动注入

**push 侧**（`push.ts`）：扫描各 AI 工具目录（teamai.yaml 的 `toolPaths`）找出 new/modified 的 skills/rules/env/agents → 交互式选择 → 建分支 → `createPrWithFallback()` 经 provider 抽象创建 MR（GitHub / TGit / CNB，reviewer 在 teamai.yaml 声明）。推送新 skill 时自动补全 SKILL.md 的 YAML frontmatter（name/description）。

**pull 侧**（`pull.ts`）：SessionStart hook 后台触发 → `lastPullRev` 未变则跳过 → 按 toolPaths 复制到各工具目录（tombstone 清理已删资源 + 角色/namespace 过滤）→ 用 section 标记注入 CLAUDE.md（团队文化 / 共享指令 / recall 规则块）→ 重建 search-index → 部署内置 skills 与 `teamai-recall` subagent。

**hooks 与 MCP 也是团队资产**：`hooks/hooks.yaml` 声明自定义 hook（事件 + matcher + command + 目标工具），`mcp/mcp.yaml` 声明 MCP server（密钥用 `${VAR}` 占位），pull 时按各工具原生格式写入。这意味着团队的"AI 工作方式"整体版本化、可评审、可回滚。

**设计要点**：分发单位是文件 + 声明式清单，注入目标是各工具的既有约定目录（`~/.claude/skills/` 等），不要求目标工具支持任何 teamai 专有协议——这是它能覆盖 28 个 AI 工具（known-agents 注册表）的原因。

### 3.2 经验沉淀：摩擦信号评分（本项目最精巧的机制）

链路：Stop hook → `hook-handlers.ts` → `contribute-check.ts` 的 `contributeCheckForSession()`。

**四类信号**（`dashboard-collector.ts` 的 `scanTranscriptStop()`，Stop 时全量扫 transcript JSONL，幂等累计快照）：

| 信号 | 识别方式 | 分值 |
|------|----------|------|
| interrupt | 用户消息以 `[Request interrupted by user` 开头 | ×20 |
| toolReject | `tool_result.is_error=true` 且含拒绝标记文案 | ×20 |
| correction | stop 后 60s 窗口内的下一条 prompt 命中纠正关键词（中英文：不对/错了/wrong/redo…），每个 stop 只消费一次 | ×20 |
| toolError | is_error 但非权限拒绝（真实工具失败） | 3 次→10、5 次→18、8 次→25（分档） |
| 规模加分 | skill 使用 +5、工具多样性 +5 | **上限 10，永远凑不满阈值** |

**阈值与防误报**（常量在 `types.ts`）：

- `CONTRIBUTE_SMART_THRESHOLD = 20`，只有摩擦信号能触达；
- 硬门槛 `toolCount ≥ 15`（`CONTRIBUTE_BASE_THRESHOLD`）——摩擦再重，没干够活也不提示；
- 规模加分上限 10 的设计从数学上保证"又长又顺（工具调用很多但无摩擦）的 session 必然不触发"；
- 每 session 状态文件记 `contributed`/`hinted`，最多提示一次；5 分钟 debounce 防重复读取。

**Phase 2 调整**（`applyPhase2Adjustments`）：本次 session 的 recall **全部 miss（知识空白）+20**、最高分 <5 +10——检索失败本身成为沉淀触发信号，与 3.3 的 recall-quality 埋点构成闭环。

达标后 `buildHint()` 输出实际触发的非零摩擦原因 + 脱敏单行任务摘要，引导用户跑 `/teamai-share-learnings`。

**沉淀执行**（`skills/teamai-share-learnings/SKILL.md` + `contribute.ts`）：纯提示词 skill，指导 AI 回顾 session、产出带 frontmatter（title/author/date/tags）的 markdown、以 sub-agent 运行避免污染主上下文，然后 `teamai contribute --file` 写入团队仓扁平 `learnings/` 目录（文件名 `<slug>-<日期>-<6位随机>.md`）。**直推 master、不走 MR**（知识条目轻量，区别于 harness 资源）；推送失败降级本地 commit、下次 pull 重试；成功后立即重建索引，新条目不用等 pull 就能被 recall。

**脱敏**（`utils/redact.ts`）两层：env 中疑似密钥变量值的字面掩码（名字含 TOKEN/KEY/PASSWORD…）+ 14 组形状正则（sk-ant- / ghp_ / AKIA / JWT / Bearer / 连接串密码），替换为 `<REDACTED:label>`。团队上传默认**只传计数和工具名**，prompt 文本需 `--include-prompt` 显式 opt-in。

### 3.3 知识检索：teamai recall

**索引**（`utils/search-index.ts`，version 6）：覆盖 learnings/docs/rules/skills 四类 md，`entryFromMdFile` 生成 `title:`/`tag:`/`type:` 前缀 token + 全局 df 表（title×3、tag×2、body×1 加权）；聚合投票分（recalled×0.3 + upvoted×1.0）、4×4 查询感知域加权、hot/cold 惩罚。有防呆保护：新索引条目数 <旧索引 20% 时拒绝覆盖。分词器 `utils/tokenizer.ts` 自研：`Intl.Segmenter(zh-CN)` + camelCase 拆分 + CJK bigram（只拼相邻单字避免幻觉词），注释里明确"增 token 必须 bump 索引版本"的维护纪律。

**排序**（`code-knowledge-recall.ts`）：自研 BM25（k1=1.5、b=0.75、idf 标准式、title 命中 +3.0），语料统计每次查询现算。图谱增强是**朴素的加性 boost**（不是 PageRank）：query token 对节点 slug/title 子串匹配定入口节点，页面命中入口节点 +8；1 跳邻居 boost = 关系权重{DEPENDS_ON:3, REFERENCES:2, MAPS_TO:2, CONTAINS_TO:1}×0.8，2 跳 ×0.4，取 max。codebase 结果分经 `min(10, log2(s+1)×2)` 压缩后与 learnings 混排（源码 TODO 自认两尺度不可比）。

**面向 Agent 的输出设计**（值得逐条借鉴）：

- `Matched: … | Missing: …` 行：结果未覆盖全部查询词时明示缺了哪个词，README 明说"这个判断由调用方做，分数本身无法表达"；
- `--check` 相关性预检：subagent 先快速判断任务与团队知识是否相关，无关直接跳过检索（省 token）；
- 三档 `--depth route|context|lookup`（token 预算 2k/5k/20k），按任务复杂度取量；
- 输出 `--- [teamai:recall:start] ---` 定界块 + 命中 codebase 页附 `Sources:` 源文件路径（直接作为代码改动入口）+ 末尾 "Candidate change files"（图的正向依赖边推导）；
- 同标题/日期/作者/内容的条目合并去重。

**检索时机经历了三代演化**（这段历史比功能本身更有价值）：

| 代际 | 机制 | 结局 |
|------|------|------|
| 第一代 | PostToolUse hook：每次 Bash/Grep/WebSearch/WebFetch 后被动自动检索 | **已移除**（CHANGELOG Unreleased）：噪音大、命中率低、与主动检索重叠 |
| 第二代 | SessionStart auto-recall 提案 | 设计文档中标记 SUPERSEDED |
| 第三代（现状） | `teamai-recall` subagent：任务开始前主动检索，`--check` 预检 + 双语关键词扩展（中英互译补召回）+ 按复杂度选 depth + 返回压缩摘要保护主会话上下文 | 保留；`recall enable/disable` 一键部署/移除 |

教训很明确：**被动、高频、事后的检索注入是失败的；低频、事前、由 Agent 主动发起的检索才成立。** 该功能默认关闭、团队可设默认开启、成员可本地覆盖——对"侵入 IDE 行为"的功能保持克制。

**检索质量埋点**（`recall-quality.ts`）：每次 recall 写会话级缓存（count/topScore/hitCount/missCount，TTL 24h，best-effort 永不抛错）；Stop hook 的 contribute-check 读取它做知识空白检测（+20 分）。**检索质量不是用来评测的，是用来触发知识贡献的。**

### 3.4 代码知识图谱：teamwiki

`teamai import --from-repo/--from-org` 把源码仓解析为 `teamwiki/` 下的结构化图谱。

**数据模型**（`wiki-engine/core/graph-index.schema.ts`）：`GraphIndex {nodes, edges}`。节点 15 种类型（architecture/component/interface/flow/data/config/error/rule…），带 confidence 与 domain；边 7 种关系（DEPENDS_ON/IMPLEMENTS/MAPS_TO/CONTAINS/REFERENCES/CONFLICTS_WITH/SUPERSEDES），带 weight、evidence 数组和 provenance 枚举（code-ast / code-heuristic / doc-* / bridge-reconcile / manual-mapping）——**实际代码路径只产出 code-heuristic 和 bridge-reconcile，code-ast 是预留**。

**存储全是纯文件、git-friendly**：全局图 `teamwiki/.indices/graph-index.json`；每仓 `evidence/code/<slug>/` 下一组 Markdown evidence 页（component/interface/config/error/relation/dependency-paths/modules/overview…）+ `_manifest.json`（AI 编译器与确定性编译器的契约）+ 缓存；顶层导航 `router.md`/`index.md`/`hot.md`；`source-manifest.json` 记录每个文件的 sha256 + headSha + ingestedMrs 作为增量基线；`gaps/detected.md` 记录知识缺口。

**解析不用 AST、不调 LLM**（`code-collector.ts` + `extractors/{typescript,go,python,java,rust,config}.ts`）：遍历源码（默认 maxFiles=200、单文件 <256KB、关键文件优先、排除 .env/密钥），逐行正则提取 `CodeFact {kind, name, file, line, detail, confidence}`；`interface-scanner.ts` 正则规则表识别 HTTP/MQ/RPC 接口（HIGH/MEDIUM/LOW 置信度）；`call-chain-tracer.ts` 按命名启发式分 entry/orchestration/service/data 四层、沿 import 追踪深度 ≤4。依赖边是**字符串包含启发式**（import target 去前缀后看是否被文件路径包含），weight 固定 0.8。取舍清楚：零依赖、确定性、跨 6+1 语言、离线可跑，代价是只认行首声明、依赖边有误报。（源码里还有一处跨仓边检测规则匹配 `relation==='imports'` 而图里实际只有 DEPENDS_ON——基本是死代码，可见该模块也在快速演化中。）

**增量更新**（`code-incremental.ts`）：基线是 source-manifest 的 headSha + sha256 清单；仅当工作区干净才走 `git diff --name-status -M -C` 快路径（rename 拆成删+增），否则回退全量 sha256 比对（注释解释：脏树对 commit-diff 不可见）。增量提取 = 剪掉变更文件的旧 fact → 合并新 fact 去重。

**健康检查**（`codebase-wiki-lint.ts`）：graph-index 可解析性、evidence 非空、导航三件套、manifest lastScan >60 天报 stale、图连通性 <30%、"节点 >10 但 0 边"；high 级问题 exit 1 供 CI 阻断。

**LLM enrich 全可选**（`enrich-with-ai.ts` / `deep-enrich.ts`）：两级 enrich（模块级 domain/responsibilities/layer/summary → 仓库级描述）、5 阶段 deep-enrich（组件设计文档 → architecture.md → 确定性文档 → mermaid 序列图 + 3-hop 爆炸半径 → 索引增强），`_review/progress.json` 断点续传。AI 写的叙事追加到 overview.md 的 `## AI Architecture Narrative` 段——**确定性产物与 AI 产物分区存放、分别标注**，这与 CodeWiki 的 Evidence-Based/source_type 标注思路一致。

**与 CodeWiki 的能力差距**：teamwiki 没有真正的 AST、没有方法级粒度、没有调用图精度、没有跨服务静态匹配（只有跨仓文件名启发式），它的图谱更像"代码事实的倒排目录"而非依赖图。这一层 CodeWiki 全面领先，不需要反向借鉴；但 teamwiki 的**纯文件存储 + manifest 契约 + provenance/confidence 贯穿 schema** 的轻量工程风格值得注意。

### 3.5 投票与知识生命周期维护（对 CodeWiki 价值最高的一节）

**票从哪来**（`votes.ts`，v2 双计数 + deltas 增量 schema）：

- `recalled`：recall 命中自动 +1（隐式票）；
- `upvoted`：Stop hook 用 `transcript-parser.ts` 从对话里解析 `<!-- teamai:referenced-doc-ids: [...] -->` 注释——即 Agent **实际引用了**哪条召回结果（采纳信号）；若召回了却没声明，用 marker 文件**只 nudge 一次**提醒主对话补声明；
- 本地存储（`~/.teamai/votes/`），pull 时 auto-report 捎带同步团队仓（per-user 文件，天然无冲突）。

**排序消费**：`score += min(票数×0.5, 5)`；同时进入下面的置信度计算。

**维护五件套**（`src/maintenance/`，752 行）：

| 模块 | 机制 | 关键参数 |
|------|------|----------|
| `confidence.ts` | confidence = base×0.4 + recency×0.3 + ratio×0.3；base = min(1, recalled×0.1 + upvoted×0.3)，recency = 1 − 距上次召回天数/180，ratio = upvoted/recalled。写回 frontmatter 时变化 ≤0.05 不动（防 churn） | 180 天衰减窗 |
| `hot-cold.ts` | 索引标注冷热：confidence ≥0.5 → hot（1.0）；<0.5 → cold（0.3 惩罚）；无数据的新文档中性 1.0 | 阈值 0.5 / 惩罚 0.3 |
| `prune.ts` | 淘汰候选：confidence <0.15，或（>180 天 且 <0.3）；支持 dry-run / archive 到 `learnings/_archive/`；**跳过无投票数据的新文档** | 0.15 / 180d |
| `promote.ts` | 晋升正式知识：confidence ≥0.90 且 upvoted ≥5 且 ≥2 用户 且 ≥14 天 → AI 按目标类别重写（skill→SOP、rule→约束+理由、docs→参考文档，去除具体日期/人/事件），原文件标记 `promoted_to` | 0.90/5票/2人/14d |
| `quality-update.ts` | **高频召回但低采纳**（recalled ≥5 且 upvoted ≤1 且 ≥2 用户）→ 找出同期真正被采纳的 learnings 作为上下文 → LLM 重写该条目（"内容相关但不够 actionable"），输出草稿供人审 | 5/1/2 |

这五件套把"知识生命周期"从**基于时间的过期**（CodeWiki 现行 stale_after 思路）升级为**基于使用证据的演化**：被反复召回且被采纳的晋升，被反复召回但不被采纳的重写，无人问津的淘汰。特别是 quality-update 的"召回多、采纳少 = 内容不行"信号，是一个 CodeWiki 完全没有的质量维度。

### 3.6 CI 集成：MR 维度的知识提取

`teamai ci extract-mr`（`src/ci/extract-mr.ts`）两个模式：

- `--mode comment`：PR 创建/更新时，spawn 本机 Claude Code CLI 提炼 MR 中的知识建议，以评论贴到 MR 上；
- `--mode write`：PR 合入后，将 learning / codebase 更新 / 图谱建议写入团队知识仓库。

配套 CI 模板三份（`examples/ci/`）：GitHub Actions 版、腾讯智研/TGit 版、以及 `codebase-lint.yml`（PR 触碰 `teamwiki/**` 或定时 cron 跑 `teamai codebase --lint --severity high --json`，产物上传 artifact）。

**意义**：这把知识沉淀从"会话结束后"扩展到"代码评审时"——MR 是团队知识密度最高的时刻之一（为什么改、改了什么、有什么坑）。CodeWiki 目前没有任何 MR/PR 维度的入口。

### 3.7 遥测、周报与 Dashboard

- **session save**（`session-collector.ts`）：折叠会话事件为摘要，`isValuable` = 有干预或 distinctTools≥3；写月度 markdown 日志（幂等标记防重复），本地 90 天保留，`--push` 传团队仓 `sessions/<user>/`。
- **digest 周报**（`digest.ts`）：**纯只读聚合、无 LLM**——skill 用量（stats/*.yaml）、近 7 天 learnings（按文件名日期过滤）、skill changelog（`git log --since=7days`）、团队人均干预率排名（作为"AI 自主性"指标）、prompt/token 排名。
- **dashboard**（`dashboard.ts`）：本地 HTTP + SSE 实时推送，事件溯源重建会话（5min idle / 30min stale），PID 存活监控补 `process_exit`（Stop 只表示 LLM 答完，不等于会话结束——细节到位）。
- **上报通道**：pull 时自动上报（`team-push.ts`），靠本地快照算正增量、天然幂等；单仓模式走 `teamai-reports` 孤儿分支 + 隔离 worktree（`utils/reports-branch.ts`），push 竞争 fetch+rebase 重试 ≤5 次，靠"每人只写自己的 `<user>.yaml`"保证无冲突。

设计文档里明确的取舍：所有 I/O try-catch + graceful degrade（"零静默失败"）；**不做贡献者排行榜**（竞争性排名伤害团队文化）；不做 ML 推荐（简单频率推荐够用）；不做 web 前端。

### 3.8 团队治理：角色、命名空间、scope 分层

- **roles**（`roles.ts` + `manifest/roles.yaml`，zod 校验）：每个角色声明 knowledge/skills 两类命名空间；pull 时过滤 rules（带 namespace 前缀的只留激活的）、skills 只同步激活命名空间并**反向删除**非激活的。**learnings 刻意不分命名空间**——注释明说经验无边界、harness 资源才隔离。
- **scope 分层**：user scope（`~/.teamai`）vs project scope（`<project>/.teamai`，v0.20 后默认）。`--inherit-user-scope` 时项目继承 user 的 skills/rules/docs/agents，但 **env/hooks/MCP 等可执行配置保持隔离**（安全边界）；recall 时 project 索引优先、再搜 user，标注 `[project]`/`[user]` 来源，继承的 user 命中只读、不 upvote。
- **跨团队订阅**（`source.ts`）：`teamai source add <repo>`，只安装对方 `publicSkills` 声明的 skills，`installed.json` 记录来源、remove 精确清理。

---

## 四、与 CodeWiki-CN 的系统对比

### 4.1 知识飞轮对照

```
teamai 飞轮（使用信号驱动）：
  session 摩擦评分 ──提示──▶ /share-learnings ──▶ contribute 直推 master
        ▲                                              │
        │                                    pull 时重建索引
  recall 全 miss(+20)                                  ▼
        ▲                                        teamai recall
        │                                              │
  quality-update ◀── recalled多/upvoted少 ◀── 投票回流（recalled 隐式 + upvoted 采纳）
  prune ◀── confidence < 0.15        promote ──▶ confidence ≥ 0.90 → 正式知识

CodeWiki 飞轮（评审闸门驱动）：
  对话/调试 ──capture_conversation──▶ raw/（只落盘）
                                        │ distill_conversation（Mode C，显式）
                                        ▼
                              ingest_note（status=draft）
                                        │ confirm_note / reject_note（人工闸门）
                                        ▼
                        query_wiki（BM25 + wikilink 多跳 + authority）
                                        │
                                        ▼
                        retrieval_stats.db（热度遥测——目前只写不读）
```

两条飞轮的关键差异：teamai 的飞轮有**自动触发器**（摩擦评分）和**使用反馈回路**（投票→排序/维护），CodeWiki 的飞轮触发靠 prompt 自觉、反馈回路在 retrieval_stats.db 处断开。CodeWiki 的优势在**闸门质量**（confirm/reject + OKF 生命周期 + lint 16 项）和**知识深度**（AST 级文档、Evidence-Based 断言）。

### 4.2 检索能力对照

| 检索特性 | CodeWiki-CN | teamai-cli |
|----------|-------------|-----------|
| BM25 实现 | 自研 + jieba 中文分词（SQLite 倒排） | 自研 + Intl.Segmenter + camelCase + CJK bigram（JSON 索引） |
| 图增强 | wikilink 有向边 BFS 多跳（hop 0-3 + decay） | 节点入口匹配 + 1/2 跳关系权重加性 boost |
| 权重信号 | note 类型/状态 authority（0.7-1.3 钳制）、aliases 3×、severity 2× | 投票分（上限 +5）、置信度冷热（0.3 惩罚）、域加权 |
| 消费协议 | 渐进式阅读（overview/directory/detail）+ expand | depth 预算（route/context/lookup = 2k/5k/20k token）+ 定界块输出 |
| 透明度 | source_type 标注（auto/note/ingested）+ [unconfirmed] | Matched/Missing 词级透明 + Sources 源文件列表 + --check 预检 |
| 触发方式 | Agent 经 MCP 主动调用 | subagent 任务前主动检索（默认关闭可配） |
| 反馈记录 | retrieval_stats.db（不参与排序） | recall-quality 埋点 → 知识缺口检测 + 投票回流排序 |

两边各有对方没有的东西：CodeWiki 的多跳扩展和渐进式阅读更成熟；teamai 的**词级透明度（Matched/Missing）、相关性预检、token 预算、使用反馈**是 CodeWiki 缺失的。

### 4.3 评审闸门：两种路线

| | CodeWiki confirm_note 闸门 | teamai learnings 直推 |
|---|---|---|
| 质量控制时机 | 事前（进检索前必须确认） | 事后（先进检索，靠投票淘汰/重写） |
| 摩擦 | 高（每条都要人确认） | 低（贡献即生效） |
| 风险 | 确认积压、飞轮转不动 | 低质知识短暂污染检索 |
| 补救手段 | reject_note | prune / quality-update / MR 评审（仅 harness 资源） |

teamai 敢于直推的前提是它有完整的事后维护链路（3.5 五件套）。CodeWiki 如果要降低确认摩擦，需要先补上事后维护能力，否则两头落空。

### 4.4 CodeWiki 领先、无需借鉴的方面

为避免"外来的月亮圆"，明确列出 CodeWiki 占优的维度：代码解析（tree-sitter AST vs 正则）、文档质量保障（Evidence-Based + unsupported_claims lint + 16 项检查 vs 6 项图健康检查）、知识规范（OKF v0.2 生命周期 + 类型化页面路由 vs 扁平 learnings）、任务记忆（跨会话任务上下文，teamai 无对应物）、跨服务分析（monorepo HTTP/MQ 调用追踪 vs 跨仓文件名启发式）、渐进式阅读协议。teamwiki 作为代码知识引擎不构成竞争参考。

---

## 五、借鉴清单（按优先级）

### P0 —— 高价值、可直接落地

**1. 摩擦信号触发机制：给"纠正识别"装上传感器**

现状：CodeWiki 的经验沉淀触发完全依赖 AGENTS.md 中的 prompt 规则（"被纠正时反思→起草笔记→征求确认"），靠模型自觉，漏报率高。
借鉴：移植摩擦评分思想到 `capture_conversation` / distill 链路——从 transcript 客观痕迹（用户打断标记、tool_result is_error、纠正关键词窗口）计算摩擦分，达标时在会话结束提示"本会话可能含值得沉淀的经验"。实现要点：
- 信号采集放 `_ide_hook.py` 的 Stop/SessionEnd 处理（幂等全量扫描，参照 `scanTranscriptStop`）；
- 阈值机制照抄：摩擦项权重高、规模项封顶凑不满阈值、toolCount 硬门槛、每会话只提示一次；
- 提示只是入口，沉淀仍走 distill_conversation Mode C + confirm_note 闸门（保留 CodeWiki 的质量优势）。
估算：2-4 人日（信号采集 + 评分 + 提示文案，不涉及存储改造）。

**2. 使用信号驱动的知识生命周期：让 retrieval_stats.db 活起来**

现状：`retrieval_stats.db` 记录检索热度但只写不读（且 gitignore 本机私有）；新鲜度专项（docs/新鲜度机制设计方案.md）的 stale_after 是纯时间窗。
借鉴：teamai maintenance 五件套的公式都是简单线性组合，可整体移植到笔记体系：
- query_wiki 命中/被引用时更新 recalled/adopted 计数（adopted 信号可用"Agent 在后续回复中引用了笔记路径"的弱判定，或先只做 recalled）；
- stale_after 到期判定时叠加使用证据：近期被召回过的笔记降级为"复核"而非"过期"；无人问津的按置信度排序进 lint 的 stale_notes 输出；
- confidence 公式（base/recency/ratio 三项加权）可直接作为 stale_notes 检查项的排序依据。
注意：热度数据本机私有 vs 团队共享是个取舍点——teamai 靠 per-user votes 文件 + pull 捎带同步解决，CodeWiki 若要走团队共享需先解决 repowiki 分发问题（见 P2-9），第一步可先做本机版。
估算：3-5 人日（与新鲜度专项 F1-F3 合并实施最经济）。

**3. 检索透明度三件套：Matched/Missing + 预检 + depth 预算**

现状：query_wiki 返回 snippet，Agent 无法判断"这条结果到底覆盖了我的查询意图没有"。
借鉴：
- 结果附 `matched`/`missing` 词表（BM25 已有 df 信息，成本极低）；
- 增加 `mode="check"` 轻量预检（只返回 top 分数与标题，供 Agent 决定是否深入）；
- detail 模式支持 token 预算参数（对应 route/context/lookup 三档）。
估算：2-3 人日。

### P1 —— 中期，依赖 P0 或需要新基建

**4. 采纳信号与投票回流**：referenced-doc-ids 注释约定（Agent 引用召回结果时声明 doc id → 解析为 upvoted）+ nudge-once。这需要 Agent 侧配合（可写入 AGENTS.md 约定或 distill 产物约定），先在本机闭环验证。

**5. "召回多、采纳少"质量信号**：quality-update 的思路——被反复召回却从不被采纳的笔记，说明标题相关但内容不 actionable，列入 lint 新检查项（可附 LLM 重写建议）。这是 CodeWiki 16 项检查没有的全新质量维度。

**6. promote 晋升机制**：高置信笔记（多用户、多次采纳、足够树龄）提示晋升为正式 wiki 页面（entity/concept 页），AI 重写去个人化。对应 CodeWiki 的 notes → wiki/ 升级路径，目前这条路径是纯手动的。

**7. MR/PR 维度知识提取**：参照 `teamai ci extract-mr` 的 comment/write 双模式，在 PR 评审时提炼知识建议、合入后沉淀。CodeWiki 有 distill 管线可复用（把 PR diff + 讨论当作 raw source），但需要 CI 侧的宿主（GitHub Actions / 内网 CI），属于产品方向决策。

**8. subagent 化检索分发**：teamai-recall 证明了一种不依赖 MCP 的集成形态（markdown 定义的 subagent + 规则注入 CLAUDE.md）。CodeWiki 若要对不支持 MCP 的环境（或部分 CLI Agent）输出检索能力，可以把 query_wiki 包一层 CLI 定界输出 + subagent 定义文件。当前 CodeBuddy/Cursor 均有 MCP，优先级不高，留作备选。

### P2 —— 长期 / 取决于产品方向

**9. 团队分发模型**：如果 CodeWiki 要服务多人团队，teamai 的三层设计值得整体参考——知识资产随业务仓（`.teamai/` 或现有 `repowiki/`）、遥测/上报数据走孤儿分支隔离、worktree 隔离 git 操作、per-user 文件避免写冲突、pull 捎带上报（正增量幂等）。这是架构级工程，先决策要不要做团队方向。

**10. digest 周报 / dashboard**：团队知识运营可视化。依赖 P2-9 的多人数据基础。digest 的"纯聚合无 LLM"原则值得保留（成本低、可离线、可进 CI）。

**11. roles/命名空间、跨团队订阅、culture 注入**：团队治理层能力，仅在团队方向确立后才有意义。

### 反向借鉴：teamai 踩过的坑与明确不做的事

| 教训 | 出处 | 对 CodeWiki 的启示 |
|------|------|-------------------|
| 被动 auto-recall hook（PostToolUse 后自动检索）被移除：噪音大、命中率低、与主动检索重叠 | CHANGELOG Unreleased | 任何"工具调用后自动触发检索/沉淀"的 hook 设计都要先过噪音关；事前主动优于事后被动 |
| SessionStart auto-recall 提案被 subagent 主动检索取代 | docs/designs/git-native-memory.md | 同上；且默认关闭、团队可配、成员可覆盖的开关策略值得照抄 |
| Stop hook 不直接调 LLM（collect-then-summarize） | docs/designs/team-intelligence-platform.md 决策 1 | hook 只做确定性采集，LLM 重活留给显式调用（与 CodeWiki "raw 只落盘不蒸馏"原则一致，互相印证） |
| 明确不做贡献者排行榜（伤害团队文化）、不做 ML 推荐（简单频率够用）、不做 web 前端 | 同上 NOT in Scope | 知识运营功能的克制清单 |
| 索引格式变更必须 bump 版本号 + 新索引 <旧索引 20% 拒绝覆盖 | search-index.ts / tokenizer.ts 注释 | 检索索引演进的防呆纪律，CodeWiki 的 search_index.json 迁移可参照 |
| Reflect 层（LLM 元分析 learnings）推迟到知识库 20+ 篇之后 | git-native-memory.md | 飞轮高级功能要等数据量就位，冷启动阶段不做 |

---

## 六、建议行动清单

| # | 事项 | 优先级 | 估算 | 依赖 |
|---|------|--------|------|------|
| 1 | 摩擦信号触发机制（接入 capture/蒸馏提示链路） | P0 | 2-4 人日 | 无 |
| 2 | retrieval_stats 接入排序与 stale 判定（并入新鲜度专项） | P0 | 3-5 人日 | 新鲜度专项 F1-F3 |
| 3 | query_wiki 透明度增强（matched/missing + check + token 预算） | P0 | 2-3 人日 | 无 |
| 4 | 采纳信号约定（referenced-doc-ids）+ 投票回流 | P1 | 3-4 人日 | #2 |
| 5 | lint 新检查项：召回多采纳少（quality-update 信号） | P1 | 1-2 人日 | #4 |
| 6 | notes → wiki 页面 promote 机制 | P1 | 2-3 人日 | #2 |
| 7 | MR/PR 知识提取 CI（方向决策后） | P1 | 5+ 人日 | CI 宿主决策 |
| 8 | 团队分发模型（孤儿分支/worktree/scope，方向决策后） | P2 | 架构级 | 产品方向 |

一个总体判断：**P0 三项都不改变 CodeWiki 的架构与评审哲学，只是给现有飞轮装上"传感器"（摩擦触发）和"反馈回路"（使用信号），并让检索输出对 Agent 更诚实。** 这与新鲜度专项的方向一致，可以作为同一阶段的增强项统筹。

---

## 附：本报告涉及的关键源码索引（teamai-cli）

| 主题 | 文件 |
|------|------|
| 摩擦评分 | `src/contribute-check.ts`、`src/dashboard-collector.ts`（scanTranscriptStop / computeSmartScore）、`src/types.ts`（阈值常量） |
| 经验沉淀 | `skills/teamai-share-learnings/SKILL.md`、`src/contribute.ts`、`src/utils/redact.ts` |
| 检索索引 | `src/utils/search-index.ts`（v6）、`src/utils/tokenizer.ts` |
| BM25 + 图谱 boost | `src/code-knowledge-recall.ts`、`src/recall.ts`、`src/recall-quality.ts` |
| 代码图谱 | `src/wiki-engine/`（graph-index.schema / code-collector / extractors / interface-scanner / call-chain-tracer / code-incremental）、`src/codebase-wiki-lint.ts` |
| 生命周期维护 | `src/maintenance/{confidence,hot-cold,prune,promote,quality-update}.ts` |
| 投票 | `src/votes.ts`、`src/transcript-parser.ts`（referenced-doc-ids） |
| 分发 | `src/pull.ts`、`src/push.ts`、`src/providers/`、`src/utils/reports-branch.ts` |
| 治理 | `src/roles.ts`、`src/source.ts`、`src/recall-toggle.ts`、`src/builtin-agents.ts`（teamai-recall subagent） |
| CI | `src/ci/extract-mr.ts`、`examples/ci/*` |
| 遥测周报 | `src/session-collector.ts`、`src/digest.ts`、`src/dashboard.ts`、`src/team-push.ts` |
| 设计决策 | `docs/designs/git-native-memory.md`、`docs/designs/team-intelligence-platform.md` |
