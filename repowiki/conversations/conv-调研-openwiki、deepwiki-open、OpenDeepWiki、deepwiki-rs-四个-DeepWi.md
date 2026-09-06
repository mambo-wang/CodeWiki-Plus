---
type: Conversation
title: "conversation 20260906T080846Z"
status: distilled
stale_after: 2026-12-05
generated: { by: codewiki/5.5.0, at: 2026-09-06T08:08:46Z }
captured_at: "2026-09-06T08:08:46Z"
content_hash: "sha256:5086dfd895681efcdd0a2605fcab0ca2c5dcd500e6cc913b415e3e93383f543b"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=4"
keep_raw: false
link_to: ""
source_session: "qwenwork-mtpcvqihrpgf2088"
turn_count: 9
---

# Conversation Transcript

user: 调研 openwiki、deepwiki-open、OpenDeepWiki、deepwiki-rs 四个 DeepWiki 类开源项目，与 CodeWiki-Plus 做五项目对比，产出可借鉴点调研报告。
assistant: 跳过任务关联。clone 四仓（commit 时点 2026-08-15~09-04），四个后台子代理并行读源码产出 notes/*.md（全部带文件:行号依据）。关键事实：①deepwiki-open 是 Next.js 反代 + Python FastAPI/AdalFlow 双进程，FAISS 单路召回无 rerank，缓存键无 commit hash 无增量，纯 Web 无 MCP；②openwiki 零静态分析，LLM agent 读文件，四层增量机制（git HEAD no-op/sha256 源指纹/页级 checkpoint/Grounded Claims preflight），确定性收尾 finalizer；③OpenDeepWiki 无 AST，LLM+ReadFile/ListFiles/Grep 三件套，DB 租约+槽位+心跳集群调度，MCP 带 OAuth 2.1+用量统计；④deepwiki-rs 已转向后继项目 Terrain 维护态，正则冒充 AST、宣称并行实际串行、死旗标、缓存不校验 model_name——README 与代码多处不符。GitHub 元数据：17.9k/16.2k/3.6k/1.7k 全 MIT。产出 docs/DeepWiki类开源项目对比调研报告-2026-09.md：六维度对比表+宣传水分清单+B1-B10 借鉴清单（排除已落地的 D1-D5）。验证子代理核查 16 项代码引用全一致，修正 2 处路径层级。结论：四竞品全走 LLM 直读路线，CodeWiki 的 AST 调用图是唯一稀缺资产；知识治理仅 CodeWiki 与 openwiki 认真做。
user: 报告 B2/B6/B1 三件事做完后各有什么收益？
assistant: B2=LLM 调用缓存省钱提速+token 可观测；B6=stale_evidence 回灌增量决策补盲区（共享池页 git diff 摸不到），D1/D2 投资回本；B1=索引内链确定性收尾自愈。三件连成一条线：重跑便宜→范围精确→产物干净。
user: 用 grill-with-docs 对 B2/B6/B1 设计拷问。
assistant: 读 grill-with-docs SKILL.md 发现是薄壳（调 grilling+domain-modeling）。代码核对发现三处调研报告偏差：B2 痛点过重（analyze_repo 已有 no_changes 短路+affected_modules 限定，且模块生成是 agentic 多轮调用，MD5(prompt) 缓存不适用，只能做模块级指纹缓存）；B1 一半已存在（analyze_repo:380 与 doc_writer:1577 已调 rebuild_index，真实缺口仅 generate_docs 无收尾）；B6 挂点=_enrich_stale_pages 之后。两轮拷问 7 问拍板：Q1 页面清单+状态分布进 changes_info（明细留 lint）；Q2 抽公共函数 collect_evidence_drift 放 evidence.py 单点收敛，lint 改薄包装；Q3 no_changes 路径静默（用户拍板，与 stale_pages 行为不对称是接受的取舍，ADR-0005）；Q4 hint 引导复核+re-stamp 不引导重写（守证据只驱动提醒红线）；Q5 stale_pages 与 stale_evidence_pages 并存不去重；Q6 新增 _enrich_stale_evidence 与 D2 后置步对称；Q7 测试五项+不触发接口同步规则。
user: 不做 B2/B1 了，只做 B6。全部按推荐。确认无误，按 1-4 开始实现。
assistant: 实现：evidence.py 新增 collect_evidence_drift（entry 级明细 file/resource/status，跳过无 content_hash 存量页与 scratch/raw 目录，复用 evidence_roots 多根解析）；wiki_lint.py _check_stale_evidence 改薄包装（行为与既有测试不变）；analysis.py 新增 _enrich_stale_evidence 只挂 handle_analyze_repo 变更路径（发现 _build_no_change_response 里误挂后撤掉，显式不调并注释指向 ADR-0005）。测试 tests/test_stale_evidence_signal.py 10 项（漂移矩阵/存量页跳过/no_changes 静默/与 stale_pages 共存不去重/lint 薄包装回归/colocated 冒烟），中途修两处测试自身 bug（gone.py stamp 前不存在、Fresh 页误引被改的 calc.py）。定向回归 119 过+ruff 过；用户中断全量 pytest，确立定向验证偏好。产出 ADR-0005 与调研报告勘误段（勘误不改正文，记录调研报告与代码现实的差距作镜鉴）。提交 784e285（B6 实现）+ 626d684（调研报告+系列12文章）。
assistant: （会话另含：公众号系列12文章《四个DeepWiki复刻的源码横评——谁在做工程谁在做Demo》的写作，humanizer 去AI味，编号续接系列11，8.6k字，修正一处无依据的'两年前'时间表述；用户偏好：子代理跑完直接写报告不确认、全量测试改定向）
