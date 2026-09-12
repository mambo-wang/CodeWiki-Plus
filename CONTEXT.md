# CONTEXT.md

> Domain glossary and key decisions for this repo. Created by the engineering skills setup.
> Populate this lazily as terms get resolved — see `docs/agents/domain.md` and the
> `/domain-modeling` skill. You don't need to fill it in upfront.

## Glossary

**task memory** — 任务作用域的进度知识（本次做了什么、下一步、待办），累积于该任务的
memories，生命周期挂在任务上：一条任务记忆无论多老都只对该任务有意义，不按"年龄"晋升
为全局知识。与 Wiki 笔记（跨任务的通用经验，全局作用域）分轨互补。蒸馏直写落盘，不经
确认闸门（ADR-0002）；笔记的闸门保留。

**memory compaction** — 记忆巩固操作：把任务记忆中的旧条目有损压缩为文件头部摘要段，
并保留最近条目全文。产出直写不走确认闸门——它是可逆操作（原文全在 memory archive，
摘要不合格重跑一次即可），不属于"噪声知识进库"的闸门防御范围。

**memory archive** — 被压缩条目的原文存放地（memories-archive.md，append-only）。永不
进入任何自动加载路径，仅供人查证或压缩返工时回溯。

**review axes** — review_changes 代码审查的四类评审依据的规范短名，focus 枚举、上下文包
evidence 键、报告 axis 字段三处统一使用：`spec`（SPEC/设计文档）、`convention`（项目
Wiki 规范 + Doctrine）、`module_knowledge`（模块历史笔记）、`general`（内置通用
checklist）。评审对象 = 同一次 git 变更（since 或未提交），工具只做确定性收集与落盘，
推理外置给调用方 Agent（Doctrine 约束）。

**possibly_stale** — 对端新鲜度标注（by_file 时间线）：目标源文件的最后一次
git 提交晚于笔记日期（留 1 天缓冲吸收当天提交噪声）即为 true；判据不可得
（文件未跟踪、git 不可用、笔记无日期）时返回 null——"不知道"不是失败，不猜。
与 `stale_after`（笔记自身年龄轴）互补不替换：一个管"知识描述的对象变没变"，
一个管"知识多大了"。_Avoid_: mtime 判定（clone 场景全量假阳性，已否决）。

**file knowledge** — 文件维度的知识检索（`by_file`）：回答"改这个文件之前，
这里有哪些历史知识"。按路径段映射笔记的 related_modules/related_components，
输出只含标题、成本、状态的时间线，不含正文（渐进式披露第一层）。预检性质，
不进 usage heat 信号。

**est_tokens** — 检索结果的成本标注：展开该条全文大约要花多少 token。语义统一
不随层级变化（非 expand 结果与 expand 结果中同义）；expand 结果另有
content_tokens 表达本次实际返回量。决策提示口径，不用于计费或硬截断。
_Avoid_: 把 est_tokens 当"本次已花费"解读（那是 content_tokens / index_tokens）。

**cost_hint** — 响应级成本提示：本次索引响应约多少 token（index_tokens）、
展开前 3 条 / 全部约多少（top3_tokens / expand_all_tokens）。作用是把 expand
从盲猜变成有预算的决策；与单条 est_tokens 是两层（条目级 vs 响应级）。

**frontmatter module** — `codewiki/src/frontmatter.py`：repowiki 页面 frontmatter
的读写一体层。读侧 `parse_frontmatter`（readers accept the union of all legacy
formats：json 编码标量、YAML 流式集合 `[a, b]`/`{ by: x }`、块列表、嵌套
metadata、`- key: value` 映射项）；写侧 `render_frontmatter`（任意 dict 序列化，
2026-09 落地）+ OKF 注入/私有元数据折叠（`inject_okf_frontmatter` /
`fold_private_metadata`）。往返不变量 `parse(render(x)) == x` 以
`tests/test_frontmatter_roundtrip.py` 固化——P1-2 `files` 字段的前置项已补齐。
页面类型路由（`PAGE_TYPE_DIRS`）在 `codewiki/src/config.py`，不属于本模块。
Slugify / 文件名约定同样不属于。永久接口约束：`capture_conversation` 输出
（`conv-*.md`）的 `status` 和 `task_id` 必须保持顶层单行键——stdlib-only hook
`.codebuddy/hooks/task_session_start.py` 逐行扫描它们且无法 import 本模块。

**retrieval kernel** — `codewiki/src/retrieval.py`：检索的文本级 kernel（deep
module，2026-09 架构评审候选 #2 落地）：tokenize（jieba CJK 分词 + regex 回
退）/ snippet / ontology 同义展开 / indexable text 构建（frontmatter 字段加
权）/ authority 乘子 / usage heat。公开常量 `K1`/`B`/`STOPWORDS`。SQLite 路径
（`AnalysisCache`）与 legacy JSON 路径都坐在这个 kernel 上，排序语义不会在两
个 adapter 之间漂移。kernel 是纯文本逻辑，不持有存储。

**SearchIndex adapter** — 检索 seam 后面的两个 adapter：`AnalysisCache`
（SQLite，活跃会话或磁盘上已有的 `.codewiki/analysis_cache.db`）与 legacy JSON
索引（`repowiki/.meta/search_index.json`）。interface（`SearchIndex` Protocol：
build/search/update_file）的唯一所有者是 `wiki_search.search`——调用方（handler、
distill 去重召回、by_file 预检）不自己选 adapter。freshness gate（build-if-
missing / 三级 stale check，`_ensure_index`）同样收口在 search 入口，每
output_dir 60s 节流。cache.py 已瘦身为纯 persistence adapter，kernel 私有
import 全仓归零。

**skill** — 从已确认知识编译出的行为指令资产（SKILL.md，Anthropic Agent Skill
规范）：消费方是宿主 IDE 按 description 自动触发改变 agent 行为，与 scenario
（检索知识，agent 主动 query_wiki 按需查阅）分轨互补。两区制生命周期：草稿区
`repowiki/skills/`（进索引进 lint、不生效）→ 人工确认后 install 到生效区
`.codebuddy/skills/`（IDE 发现即生效）。修订经 `metadata.revisions` 审计链，
退役 retire 保留正文。有效性反馈收敛到既有 `flag_issue` 通道，不开平行通道。
_Avoid_: 把 skill 当 scenario 的替身——一个进系统提示改变行为，一个进检索
供查阅；素材过期联动（stale）走技能自身标注，不改写素材源。

**tri-state gate（三态门控）** — 语义归并类新能力的统一开关词汇：`off`（不采集不
生效）/ `observe`（采集并记录「本应做什么」，不改核心结果）/ `enforce`（真正改变
结果）。纪律：新能力默认 `observe`，用离线数据证明收益且无误伤后才升 `enforce`。
本仓已有等价物（draft 笔记不生效、`low_adoption` 仅 warning、lint 只报不改、采集
hook 默认关）统一归入此词汇，不另造机制；登记面见 `docs/capability-matrix.md`。
_Avoid_: 为单个能力发明第四种状态、或绕过 observe 直接 enforce。

**conflict case（冲突案卷）** — 一对互相矛盾的 Wiki 笔记的裁决记录，顶级 `conflicts/`
页面类型（ADR-0007）：frontmatter 携带 `claimants`（当事笔记）、`status:
open|resolved`、`resolution` 与裁决人/时间。是治理元数据不是知识——不进检索语料，
由检索在命中 claimant 时附加「存在未裁决冲突」标注。裁决动作集
`keep_a/keep_b/coexist/reject`，内部复用 `reject_note` 原语；账本即 git。只做
Agent 手动声明，不做自动发现（无 slot 底座 + 弱冲突误报前科，ADR-0007）。
_Avoid_: 把案卷写成普通 note（污染检索语料）、双向 `conflict_with` 引用（易漂移）。

**memory recall（任务记忆检索）** — 任务记忆的条目级按需召回（`search_task_memories`），
与注入路径（`get_task_context` 尾部整取）互补：一个管「开始任务时带什么」，一个管
「按关键词找回被截断/压缩的旧条目」。条目级颗粒度（`### 日期` 一条一索引记录），
惰性新鲜度（search 时校验 mtime 重建脏任务），archive 参与召回（压缩与检索正交：
压缩省注入成本，检索是主动付费的找回）。默认只搜本人，搜索侧隐私姿态不宽于读取侧。
自动压缩由 get_task_context 携带 compaction_work 驱动，Agent 顺手 submit，无需用户
确认（ADR-0002 直写语义延伸，可逆操作）。
_Avoid_: 把任务记忆并进 query_wiki 语料（分轨）、为索引加后台进程（成本不可见）。

## Key decisions

- [ADR-0001 — 任务记忆保持 Markdown，不迁移 JSONL](adr/0001-task-memory-stays-markdown.md)（2026-08-24）
- [ADR-0002 — 任务记忆直写落盘，不设确认闸门](adr/0002-task-memories-direct-write.md)（2026-08-24）
- [ADR-0003 — 对端新鲜度判据用 git 提交时间而非 mtime](adr/0003-possibly-stale-uses-git-commit-time.md)（2026-09-02）
- [ADR-0004 — 技能与场景分轨，两区制守确认闸门](adr/0004-skill-scenario-split-two-zone-gate.md)（2026-09-06）
- [ADR-0005 — 证据漂移信号仅在代码变更路径参与增量决策，no_changes 路径保持静默](adr/0005-evidence-drift-silent-on-no-changes.md)（2026-09-06）
- [ADR-0006 — 会话绑定凭证退役而非销毁，归属继承三级回退](adr/0006-session-binding-attribution-tombstone.md)（2026-09-11）
- [ADR-0007 — 冲突案卷是独立页面类型，不是笔记](adr/0007-conflict-case-page-type.md)（2026-09-12）
