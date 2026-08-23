# OpenViking 借鉴全景路线图（P2–P4 候选汇总）

> 来源：`docs/OpenViking-调研与借鉴分析.md` 第五节借鉴清单全量整理（P1 三项已细化为 `docs/知识飞轮增强设计方案-P2三项.md`，本文不重复其细节，只做索引与补全其余各项）。
> 日期：2026-08-22 · 状态：**部分已实施** · 章节均标注优先级、工作量与依赖，供分阶段排期。
> 实施记录（2026-08-22）：V2/V3/V4/V6/V7 已落地（309 测试全绿，真实 repowiki E2E 通过）；**V1 取消**（OKF 已有 description 标准键，无需新字段——改为对既有 description 键做规则抽取回填）；**V7 按用户决策改造**为推送式——write/edit_doc_file 更新 Wiki 后在响应中主动提醒关联笔记复核（原拉取式 lint 检查不做）。V5 挂起、V8 触发条件制、V9 已决策不做。
> 总原则（贯穿全部条目）：借粒度不借管线、借模式不借哲学——OpenViking 为 AGPLv3，只借鉴思想；其"LLM 写时摘要""无闸门直写"两条哲学性取舍明确不学，理由见各条目。

---

## 一、全景总览

| 编号 | 条目 | 借的机制 | 来源（OpenViking） | 优先级 | 工作量 | 依赖 |
|------|------|---------|-------------------|--------|--------|------|
| V1 | 目录级摘要 abstract | L0 分层加载 | `.abstract.md` sidecar + L0/L1/L2 | P2 | 1 人日 | 无 |
| V2 | 注入预算降级 | 超预算条目降为 URI+score | auto-recall.mjs | P2 | 1 人日 | V1（联动收益） |
| V3 | 字段级预合并 | merge_op 字段策略 | memory/*.yaml + merge_op/ | P2 | 1–1.5 人日 | 无 |
| V4 | 记忆类型声明式 schema 化 | YAML 声明 12 类记忆 | prompts/templates/memory/ | P3 | 1 人日 | 无 |
| V5 | 遥测出口标准化 | Prometheus exporter | metrics/ + usage audit | P3 | 1 人日 | 无 |
| V6 | 提取循环 ReAct 化 | 带工具多轮提取 | extract_loop.py | P3 | 2–3 人日 | V4 建议 |
| V7 | 新鲜度输入感知复核 | L0 未变停止冒泡 | freshness_policy.py | P3 | 0.5 人日 | 无（接既有 stale_after） |
| V8 | embedding 混合检索 | dense+sparse+目录递归 | hierarchical_retriever.py | P4（暂不动） | 架构级 | 出现真实召回缺口再评估 |
| V9 | 运行时记忆层互操作 | repowiki 作为其 resource | ov add-resource / OKF 同源 | ~~P4~~ 已决策不做 | — | — |

已实施的 P0（摩擦触发/使用反馈/检索透明）与 P1（采纳信号/低采纳检查/promote）不在本文范围——它们与 OpenViking 的对应关系见调研报告第四节"六机制独立收敛"对照表。

---

## 二、P2 档（V1–V3）：转得省

细化为 `docs/知识飞轮增强设计方案-P2三项.md`，此处只记决策要点：

**V1 目录级摘要**：frontmatter `abstract:` 字段（非 sidecar 文件，单一事实源），规则抽取首段前两句、160 字符上限，零 LLM。消费点是 reading_guide 预展开清单与 query_wiki 结果。关键约束：frontmatter 5 writer 场景下 schema.yaml / 模板 / schema_generator 三处同步，OKF 顶层白名单扩 `abstract`。

**V2 注入预算降级**：agents_md.py 与 wiki_search.py 两个注入点各配字符预算，预算内全文、预算外压为 `路径 | 分数 | abstract` 一行。adoption_hint 走降级格式。预算 0 时输出与现状逐字节一致（回归锚点）。

**V3 字段级预合并**：note_consolidation.py 对同主题 draft 组按字段策略（replace/append/sum）预合并为一条 draft，confirm 一次转正、原组批量 superseded；拒绝路径原 draft 零变化。闸门不动摇——借 OpenViking 的合并粒度，不借其直写。

---

## 三、P3 档（V4–V7）：机制升级

### V4 记忆/笔记类型声明式 schema 化

OpenViking 用 YAML 声明 12 类记忆的目录位置、文件名模板、字段与每字段 merge_op——新类型即加一份 YAML，handler 零改动。CodeWiki 的 note_type 目前散在三处：schema.yaml 配置段、各 handler 常量（如 `_ALL_CHECKS`、`PAGE_TYPE_DIRS`）、registry 枚举——三处不同步就是历史坑的来源（query_wiki type_filter 漏 "scenario" 的 live bug 即此因）。

**借法**：把"note_type → 可用状态/复核窗口/晋升路由/page_type 映射"收敛为单一声明表（可就在 schema.yaml 内做权威段），schema_generator 从表生成枚举与校验，handler 只读表。收益是类型扩展从"三处改"变"一处改"，且 V3 的字段 merge_op 策略有天然挂载点。注意：inputSchema 枚举从表生成后仍须与 MCP registry 同步验证一次（REGISTRY[name].schema.inputSchema 的枚举校验先于 handler）。

### V5 遥测出口标准化

现状 retrieval_stats.db 本机单机、只写不外露。OpenViking 三层遥测（span 全链路 / Prometheus 指标 / SQLite 用量审计）中，**只借 exporter 模式**：把已有的 hit/last_hit/adopted 三元组与 zero_result、latency（若可低成本获得）以标准 metrics 文本格式暴露（一个 `wiki_stats --metrics` 输出即可，不必起常驻服务），供 Prometheus 抓取或人肉 curl 查看。

不借 span 体系与 usage audit 新表——那是团队部署阶段的基建，当前单机场景收益不抵复杂度。此项是 V5 排 P3 的原因：为未来团队化预留出口，但不预建。

### V6 提取循环 ReAct 化（distill v2）

现状 distill_conversation 是单轮 LLM 一次性产出 notes+memories；OpenViking 的 extract_loop 是带 memory 工具的 ReAct 循环（限 3 迭代），提取中可反查已有记忆再决定 upsert 还是 patch。

**借法**：distill v2 给 LLM 一个只读 `query_wiki` 工具，两轮迭代——第一轮照常提取，第二轮把候选笔记与库内现有笔记查重对照，输出合并建议（引用既有 note_id）而非新条目。产出仍走 draft→confirm 闸门。这项与 V3/V4 是组合拳：V4 提供"哪类笔记该怎么合并"的声明，V3 提供合机器可执行的字段策略，V6 让提取时就带上库的现状。工作量最大（2–3 人日），排 V4 之后。

### V7 新鲜度"输入感知"复核触发

OpenViking 冒泡规则的核心洞察：父摘要消费的是子项 L0 正文，**输入没变就不刷新**——复核触发看"实际输入是否变化"，而非时间窗。

**借法**：freshness v3 方向。stale_after 时间窗保留为兜底，新增提前复核信号：note 声明引用的 related_modules 文档（或 source_ingest 溯源文件）mtime/内容 hash 变化时，该 note 提前进入 pending 复核。实现是 lint _check_stale_notes 里加一个输入比对分支，半天量级。与既有"检索顺延"（被命中即延窗）构成三信号：时间兜底、使用顺延、输入触发。

---

## 四、P4 档（V8–V9）：架构级决策，暂不动但有明确触发条件

### V8 embedding 混合检索

OpenViking 用 dense+sparse+目录递归在 LoCoMo/tau2 拿到实证收益，但其知识形态（自然语言记忆、跨项目）与 CodeWiki（术语精确、wikilink 密集的代码知识）不同域，BM25+jieba+多跳在后者未必差。**触发条件**：出现"BM25 召回明显不够"的真实案例（如 lint 或用户反馈中反复出现 query_coverage 落空类问题）再立项评估。立项前可先做零成本对照——拿 repowiki 历史检索日志离线跑 embedding 召回 vs BM25 召回的差异分析，数据说话。

### V9 运行时记忆层：不进入，亦不做上游互操作（已决策）

**决策记录（2026-08-22，用户拍板）**：CodeWiki 不定位为 OpenViking 的上游知识生产者，互操作验证实验（`ov add-resource` 消费 repowiki）与 README 互操作指引均不做。理由：上游定位会把 CodeWiki 的演进方向绑定到对方生态的格式与节奏上，与"独立、自洽的单仓知识引擎"定位冲突。

不进入该层本身的技术理由不变：常驻 server、采集基建、记忆 schema 全家桶，OpenViking 以 2.9 万行专职投入且有 VLDB 论文背书，重复造性价比极低。OKF frontmatter 双方同源这一事实仍具参考价值——它验证了格式选型，但参考价值到此为止，不外溢为集成义务。

---

## 五、明确不借鉴清单（与理由）

| OpenViking 机制 | 不借理由 |
|----------------|---------|
| 无闸门直写（提取即落盘） | 与"可信知识库"定位冲突；质量全靠 merge/dedup 兜底，噪声记忆可长期留存 |
| LLM 写时摘要管线 | 违背零 LLM 依赖检索的卖点；V1 用规则抽取达到同效 |
| 自研向量库 / C++ 引擎（C/D/T 三表） | 工程量级不匹配，且 V8 未立项前无需求 |
| 独立 sidecar 文件（.abstract.md） | 人机共编场景下漂移风险；frontmatter 单一事实源更稳 |
| patch + search-replace diff 级合并 | 实现重、收益边际；replace/append/sum 三档覆盖首版需求 |
| SaaS 多租户 / 商业版体系 | 当前阶段无需求 |
| token 精确计数预算 | 注入预算是排序提示不是计费精度，字符近似足够 |
| span 全链路 + usage audit 新表 | 单机场景收益不抵复杂度，P3 只借 exporter 模式 |

---

## 六、排期建议与依赖图

```
P2（并行三线，3–4 人日）
  V1 abstract ──→ V2 预算降级（B 吃到 A 的摘要）
  V3 预合并（独立）

P3（V1–V3 落地后）
  V4 schema 声明化 ──→ V6 ReAct 提取（建议序，非硬依赖）
  V5 遥测 exporter（独立，任意时点）
  V7 输入感知复核（独立，随时可插）

P4（触发条件制）
  V8 混合检索 ← 触发：真实召回缺口案例 + 离线对照数据
  （V9 已决策不做，见第四节）
```

实施顺序建议（2026-08-22 修订，V9 撤下后）：V7 → P2 三项（V1→V2 绑定、V3 并行）→ V4 → V6 殿后；V5 挂起（单机场景收益最低，团队化有明确计划时再做）。V8 维持触发条件制。测试与 E2E 约定不变：`python -m pytest tests/ -o addopts=""`，每阶段在真实 repowiki 上跑端到端。

---

## 七、补查：docs/design 全量扫描后的剩余项结论（2026-08-22）

初版清单基于核心模块调研；本节对 `docs/design/` 全部 20 篇设计文档做了二次扫描，逐篇评估。结论：**无新增进入 V1–V9 的项**，新增四个"已覆盖/不适用/观察"结论归档如下，防止后续重复评估。

| 设计文档 | 机制 | 结论 | 理由 |
|---------|------|------|------|
| `ov-compile-design.md` | 用 Skill 把库内材料编译成 Wiki 页面 | 已覆盖 | 语义与 P1-C promote（notes→wiki 重写晋升）同构，CodeWiki 另有 generate_docs/refresh_doctrine；差异只在它跑在独立 Bot 进程 |
| `memory-link-design.md` | 记忆间有向/带权/双向链接层 | 不适用 | CodeWiki 已有 wikilink + crosslink + 多跳检索，链接层是既有能力；其"链接存 frontmatter、渲染时展开"的存储细节无增量 |
| `git-version-control-design.md` | 账号粒度知识快照（commit/restore/show） | 不适用 | 架构差异所致：OpenViking 数据在自有存储中不受益于 git，才需内嵌 gitoxide；CodeWiki 的 repowiki 本就随代码仓走 git，版本化/回滚/审计免费拥有。唯一残余念头"跨文件逻辑事务快照"（如 promote 改多文件原子化）价值低，用户 git 提交粒度即事务粒度 |
| `traj-exp-experience-learning-redesign.md` | rollout→trajectory→experience 策略训练框架 | 观察 | 唯一真正的新范式：把经验目录视为可训练的 Policy Set（analyze→estimate→plan→apply，可审查可合并）。超出知识管理进入 agent 训练域，当前无场景；其"可审查的策略更新"设计与 confirm 闸门哲学相通，列为上游动向观察 |
| `tool-stub-design.md` | 超大 tool output 规则化摘要替代 head+tail 截断 | 不适用 | CodeWiki capture 管线刻意过滤 tool 流量（只留对话轮次），不存在"截断失真"问题，也就无此需求 |
| `agent-evolution-global-switch-design.md` | 部署级开关停用某类记忆生成 | 已覆盖 | CodeWiki 等价能力是配置权重置零（如 adopted_weight=0）+ schema.yaml conventions 段；V4 落地后类型级开关进一步收敛进 note_types 表 |
| `metric-design.md` | /metrics 与 observer/stats 边界 | 已覆盖 | 即 V5 遥测出口的边界设计参考，无新增 |
| `resource-ingestion-routing.md` / `mcp-oauth2-1.md` / `parser-two-layer-refactor.md` / `openclaw-agent-experience-memory-design.md` / cuVS / llama-cpp / usage-reporter-sink 等 | 各自工程实现细节 | 不适用 | 纯内部实现文档（解析路由、鉴权、GPU、本地推理等），无跨项目借鉴面 |

另有两个 README 层机制未入清单，记录理由：**watch 订阅**（list_watches，目录变化触发重新 ingest）——CodeWiki 知识变更全部经自身工具链，无外部写入源，无 watch 需求；**VLM 多模态解析**（vlm.py，图片理解）——CodeWiki 域是代码与文档文本，暂无图像知识场景。

**净结论**：V1–V8（V9 已决策不做）加上"明确不借鉴"清单与上表，构成 OpenViking 对 CodeWiki 可借鉴性的完整覆盖。真正值得长期盯的上游动向收敛为两处：traj-exp 经验学习框架（若未来做 agent 经验训练）与 l0-l1-okf-sidecars RFC 的 OKF 演进（仅作格式选型参考，不构成集成义务）。
