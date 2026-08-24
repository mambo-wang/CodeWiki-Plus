---
type: Conversation
title: "conversation 20260824T050116Z"
status: distilled
stale_after: 2026-11-22
generated: { by: codewiki/5.4.2, at: 2026-08-24T05:01:16Z }
captured_at: "2026-08-24T05:01:16Z"
content_hash: "sha256:739439fd558e3f804e6405be19d0d81b25ded433b4ca1d97cd71b59c441aaa9f"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=6"
keep_raw: false
link_to: "OpenViking-调研与借鉴分析"
source_session: "qwenwork-mt30qo374xp39696"
turn_count: 12
---

# Conversation Transcript

user: 调研 OpenViking 对比 CodeWiki
assistant: 完成 volcengine/OpenViking 调研（AGPLv3，Agent 上下文数据库，viking:// 虚拟文件系统+写入时 L0/L1 分层摘要+混合检索，VLDB 2026 论文背书）。报告 docs/OpenViking-调研与借鉴分析.md + 全景路线图 V1-V9。
user: 我们也有记忆呀，跟他的相比谁的比较好
assistant: 拆轴对比：CodeWiki 强在可信度（draft→confirm 闸门+18 项 lint+stale_after，库里的知识是被审过的）与代码结构绑定（note 挂 module 进 authority 排序）；OpenViking 强在机制完整性——ReAct 提取循环（反查库现状再决定 upsert/patch）、字段级 merge_op（patch/replace/immutable/sum）、全自动闭环（触发环节是我们最弱一环）、LoCoMo 80%+ 基准背书。定位：CodeWiki=少而精跟仓库走人审过（知识库），OpenViking=多而活跟用户走全自动（运行时状态）。闸门哲学不丢，三个机制级优势可低成本吸收。
user: P0 我们怎么借鉴
assistant: 三原则：L0 目录级摘要借'分层'不借'LLM'（module 文档规则抽取 overview 段，零模型成本；优先 frontmatter abstract 字段而非 sidecar 文件——sidecar 易漂移，但注意 frontmatter 5-writer 加字段须三处同步）；注入预算降级借'模式'不借'hook'（超预算条目降为 URI+score 一行，与 adoption_hint 天然搭档）；merge_op 预合并借'粒度'不借'无闸门'（同主题多条 draft 字段级预合并产出一条，人只 confirm 一次）。关系：P0 三项让飞轮'转起来'，这档三项让它'转得省'。
user: 这就是 openviking 中所有值得借鉴的项了吗
assistant: 补查 docs/design 全部 20 篇设计文档：无新增进 V1-V9 的项。三个'不借但值得知道为什么'：git 版本控制（OpenViking 数据不在 git 才需自建 gitoxide 快照，我们 repowiki 随代码仓走 git 免费拥有——架构位置不同带来的伪需求）、memory-link（wikilink+crosslink+多跳已是此能力）、tool-stub（capture 管线刻意过滤 tool 流量，问题不存在）。唯一'观察'：traj-exp 经验学习框架（经验目录当可训练 Policy Set，唯一超出知识管理进 agent 训练域的新范式）。
user: 所有 openviking 候选项中，哪些值得做？
assistant: 四档排序：立即做（V7 输入感知复核半天——解决 stale_after 时间窗盲的缺陷；V1 目录级摘要 1 人日——唯一直接省 token 且是 V2/V6 地基；V9 互操作验证半天——决定'CodeWiki 定位为 OpenViking 上游生产者'叙事成立否）；值得做有前置（V2 预算降级绑定 V1；V3 字段级预合并也是 V6 的执行管线；V4 声明式类型收敛——type_filter live bug 已证明三处同步非理论风险，1 人日消灭一类 bug）；缓做（V6 提取两轮化吃 V1/V3/V4 产出，2-3 人日压轴；V5 遥测 exporter 单机无读者挂起）；不做（V8 embedding 混合检索——无真实召回缺口案例不立项，BM25+jieba+wikilink 在代码知识域没输过）。
user: 提交推送代码
assistant: 按委托惯例分三笔提交推送 feat/team-memory-l2l3：cfb23e4 feat（五线核心：note_types/note_merge/injection_budget/doc_description/doc_update_notify 五新模块+7 处接线+2 迁移脚本，13 文件 1056 行）、35f6f55 docs（全景路线图+P3 详设）、eb77e50 chore（schema.yaml note_types 权威表+30 篇存量文档 description 回填）。telemetry E2E 噪音还原未提交；非本次产物的未跟踪文件保留未动。
