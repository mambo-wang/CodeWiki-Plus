## 早期记忆（摘要）

ADR-0013 已完成：stable 笔记入库必须带 reason（draft/confirm 豁免）；可选 test_ref/commit_ref/reviewed_by 映射 metadata.verification 与强置信度；未知 evidence key 拒绝。limits.py 集中阈值（40 条/24KB/保留 20/摘要 4096 字），threshold_drift 守护一致性。聚合 frontmatter 换行是已确认坑。

ADR-0015：AGENTS.md 收敛为精简托管块+按需路由，已推送 cb305c7。UserPromptSubmit active-settle 薄触发已实现（读 tasks/.index.json fail-open，全量 1131 passed）；PreCompact 与 Stop+block 裁决不做；SubagentStart hook 不做（subagent 无任务级视野、会绕确认闸门），改为 subagent 返回值约定写入 get_prompt(task-workflow)。Workspace Conventions 模板已瘦身（接入清单收敛到 add_workspace_repo 工具）。ide_config.py golden fixture 仍 deferred。

B4 计划写入门禁与 B5 聚类质量 validator 均为内部模块非新工具，已实施并最终验证。B4 默认 observe，enforce 仅放行 pending 页面或精确 target；授权绑定 routed page key、计划 schema/hash 与当前 centralized 分区；同 stem 跨仓归因已修复，无 key 删除拒绝 query 路径、无 key update 仅唯一安全匹配时授权；overview 只认 canonical；计划外写入落审计不污染 plan_hash；这是运营性门禁非安全边界。B5 按完整 scope 文件分块估 token，缺测/逃逸/不可读显式进 unmeasured；轻量缓存，异常降级 unavailable，不调 LLM、不自动改树。验证：B4 专项 43、B5 20、最终联合 172、全量 1538 passed/2 skipped；MCP 契约 121/5 既有基线；smoke_test_mcp.py 不跑（会写真实 repowiki）。B4/B5 草稿保持 draft，未提交推送。

C3 artifact facts 已实施验证：artifact_facts.py 接入 analyze_repo，artifact: 事实不进源码 components/依赖边/module tree；支持纯 artifact 增量、失败/截断显式化，不执行工程命令。专项 39、全量 1577 passed。C2 语言薄适配：Rust 已验收（grammar preflight、独立 wheel、trait impl 唯一身份、未知 receiver 不猜尾名，专项 25、全量 1602）；Scala/Zig 早期进度条目已被后续取代；当前继续 Ruby。各语言决策草稿均 draft，未提交推送；Lean 4 不自动展开。

技能：caveman 与 humanizer v2.11.2 已安装；Ponytail T1/T2/T3 调研已记录（CodeBuddy=T2），机制草稿被拒；wikiskill 将确认笔记转 SKILL.md 草稿再确认安装；skill-creator 走 prepare/submit/install/retire，容量 12。skill hint 裁决：architecture 笔记不在技能素材边界，不编译；「install-hooks 需用 python -m codewiki.cli.main」pitfall 信息量单薄，deferred 等同类素材并入。

调研：hindsight 重运行时路线不走；_DISTILL_SYSTEM 仅一条推理规则（reason+NO COMPUTATION）；delta refresh 与检索+RRF 仍 deferred，absorbed/deferred 项需落点与触发。graphiti/ADR-0011：malformed 输出保留 raw+parse_failed、复用中文分词、弱冲突<0.8/快路径>=0.8。llm-wiki-compator 仅借鉴 eval/freshness/atomic-intent/profile-as-data。cognee 8/8 证伪。2026-09 调研：11 项目/44 候选，0 采纳/15 deferred/29 excluded（docs/借鉴项目整体增量调研报告-2026-09.md、docs/claude-mem-增量调研与借鉴分析-2026-09.md）。agentmemory 调研存档 repowiki/wiki/queries/agentmemory-调研.md：重运行时路线不走，三候选全不立项；Round 2 定案（用户裁决「按推荐」）：CODEWIKI_TOOLS=core 裁剪开关立项 P2 归产品维护，RRF 融合与 related_notes 语义召回 excluded，同义词/CJK 分词/SHA-256 去重本仓已有。TDAM 调研（v2.0.3）：文章三层图谱/本体在开源代码零命中（内部实践未开源）；真机制为 Skill 按需选择（JEV provider、client_tool 交付、MAX_CLIENT_LOADS=3）与 team_memory.enabled 总开关；本仓实测合成消息占比均低于 20% 阈值，噪声过滤 excluded；可借鉴认知：经验带适用条件+被排除解释、失败归因四层、追踪经验是否改变行为。

2026-09-20 AGENTS.md 调研倾向精简路由（cairn ≤60 行+责任表）；task-memory 指引与 AGENTS.md/SessionStart 重复，优先 hook 硬通道+一行指针。teamai-cli golden fixtures 与 claude-mem 原生 async 候选待 CodeBuddy 验证；拒绝 claude-mem 六事件全量采集、inline-bash 路径解析与 letta commit-on-write。外部克隆放 D:/repos。subagent 笔记状态用 get_task_context 核实。commit 0ac6081（续接会话避免重复选任务）code review 通过：三级恢复+跳过终态，2 Low（raw 索引回退过时归属；异步弹框后任意文本被当答案）不阻塞。

⚠️ 作废标记：CBM workspace manifest 曾被误读为 Rust Cargo manifest，该结论已作废，不构成批准。2026-09-04 跨 Agent-skills 草稿未决。旧草稿笔记一律等 confirm_note，绝不自动确认。工具错误信号来自 _ide_hook.py/capture_conversation.py 的 tool_digest；会话结束补采绕过它，早前测得的 0% 是通道覆盖面而非漏采率。早期原文归档于 memories-archive/iamwangbao-163-com.md。

> 原文归档于 memories-archive/iamwangbao-163-com.md，截至 2026-11-28，共 13 条。

### 2026-11-27 07:09 #sdc2

C2 第二语言 Ruby 薄适配已完成并验收：独立 tree-sitter-ruby 0.23.1 + grammar preflight，保留完整 namespace、#/. 方法身份、词法常量/继承作用域与保守接收者推断；跨文件裸调用延迟解析且不做尾名猜测。两轮审查反例已修复。验证：Ruby 专项 43 passed、Ruby/Rust 68 passed、加入 correctness/latest compat 联合 81 passed；真实 Ruby 标准库 19 样本得到 956 组件/2823 关系；正式 stdio MCP 首次 16 组件。增量复测发现并修复 AnalysisCache._SRC_EXTS 缺 .rb/.rs，导致无改动全量误报；修复后 no_changes=true，单文件新增只报 support.rb 与 #report。OKF 契约 121/5 与基线一致。最终全量回归（已纳入缓存修复和两项指纹回归）为 1645 passed, 2 skipped, 1 warning。backlog 已更新，Ruby 决策草稿保持 draft。任务记忆早期摘要已压缩 1 条并保留 20 条。本轮未提交、未推送、未确认草稿；下一语言候选为 Vue SFC，但本轮停在 Ruby 收尾，不自动扩项。

### 2026-11-27 08:47 #xc95

本轮 9 篇决策草稿已由用户明确确认，全部转为 stable/strong：上游借鉴总稿、B1 反向索引、B2 ownership、B3 tree repair、B4 write guard、B5 clustering validator、C3 artifact facts、C2 Rust、C2 Ruby。confirm_note 返回 consolidation_due，但用户未授权聚合，按闸门不执行。最终全量回归为 1645 passed, 2 skipped, 1 warning。已按用户授权新建分支 feat/codewiki-upstream-b1-b5-c2-c3，准备只提交本轮相关代码、测试、清单、确认笔记与当前用户任务记忆，rebase 到最新 origin/develop 后推送。下一语言为 Vue SFC。

### 2026-11-27 09:36 #7rko

C2 第三语言 Vue SFC 薄适配已完成并验收：新增确定性 SFC 扫描器，脚本外等长掩码后复用 JS/TS analyzer，保留原文件行号；提取组件、Options API 成员、脚本函数、导入与模板组件/表达式边。组件与脚本同名时使用 path::script.Name 并重映射关系；Vue caller 仅对完整 path::symbol 放行精确跨语言命中。审查发现的插值伪标签、ID 冲突、跨语言精确解析、前 64KiB 指纹漏检均已先红后绿修复；指纹改为全文流式 SHA-256，旧缓存升级后首次可能全量重算。验证：Vue 专项 25 passed，Vue/Rust/Ruby/correctness/latest compat 联合 106 passed，最终全量 1670 passed/2 skipped/1 warning；ruff、mypy、diff check 通过；MCP 契约 121/5 与既有基线一致；正式 stdio 首次 9 组件，无变更与单文件新增 ArticleList.reset 增量均正确。backlog 已更新，Vue 决策笔记保持 draft 未确认。本轮未提交、未推送；下一语言候选 Go package-aware 仍按需求触发，不自动展开。

### 2026-11-27 10:44 #n88f

Go package-aware 薄适配已完成：保留本地组件 ID 与 route extractor，新增 directory/package 精确解析、go.mod/local replace、仓库 import 可见性、隐式 interface method-set，以及 MCP/watch 增量缓存 package 合并；外部 qualified type、同名包函数/方法、陈旧 interface 边均有回归覆盖。Go 专项 25 项、相邻联合 131 项通过；最终全量 1694 passed, 2 skipped, 1 warning（第 25 项 Go 反例在全量收集后新增，已由专项覆盖）；正式 stdio MCP 首次/无变更/单文件增量通过。边界：interface 仅按方法名集合近似，不校验完整签名/指针接收者/嵌入接口；dot/blank import 保守。下一步：保留 Go 决策草稿待用户确认；提交与推送仍需用户明确授权。

### 2026-11-27 14:06 #4yy7

C2 Scala package-aware 薄适配已完成并验收：独立 tree-sitter-scala wheel、grammar preflight、声明 package/import 精确解析、companion `$` 身份、Scala 2/3 类型/方法、wildcard 唯一命中、重载弃权、词法 receiver 作用域、缓存嵌套身份与旧边重裁决、继承基类优先及顶层后备、`super` 基类解析、构造参数字段链 package 固化；`.scala/.sc` 与 SBT manifest/service/artifact 接入已同步。三轮审查反例均有回归：Scala 43 passed、语言联合 174 passed、Scala/artifact 82 passed，ruff/mypy/diff check 通过；OKF 为既有 121/5。正式 stdio MCP 首次/无变更/单文件 5→6 增量通过，super 临时仓只连 lib.Base.work。最终全量（清除本机代理环境后）：1738 passed, 2 skipped, 1 warning。决策草稿 notes/2026-11-27-scala-analyzer-应保留组件-id-并按声明-package-精确解析.md 已可检索且保持 draft。边界：完整类型推导、宏、动态派发、重载目标选择、多基类线性化，以及跨文件同包重载/顶层后备仍保守。未提交、未推送、未确认草稿。

### 2026-11-27 15:40 #ya5h

Dart/Flutter C2 语言切片完成：独立 tree-sitter-dart wheel 与 grammar preflight，新增 dart.py/dart_imports.py/dart_flutter.py，实现 visible-scope 解析（相对与 package URI、prefix、show/hide、export 闭包、part、library 私有名、词法遮蔽、继承成员与字段链），接入 CallGraph、SQLite metadata 原始引用复核、旧缓存迁移、pubspec 语义依赖、CLI/prompt/review/服务识别/artifact facts。Flutter 仅做轻量确定性分类，不执行 analyzer 或生成代码，不承诺完整类型推导/泛型/动态派发。验证：Dart 专项 36 passed；语言/artifact/tree repair 联合 257 passed；最终全量 1774 passed, 2 skipped, 1 warning；ruff check/format、git diff --check、新增三模块 mypy 通过；OKF 保持 121 passed/5 failed 既有基线。正式 stdio MCP 验证首次分析、无变更、单文件增量、package/prefix/part 边、pubspec 改名与 artifact-only pubspec，工具总数仍 53。决策草稿：repowiki/notes/2026-11-27-dart-analyzer-应按-library-visible-scope-精确解析并持久化原始引用.md（draft，未确认）。当前代码、文档与草稿均未提交、未推送；未开始 Zig。

### 2026-11-27 16:59 #l5so

C2 Zig 语言薄适配已完成并验收：使用独立 tree-sitter-zig==1.1.2 wheel 与 grammar preflight，保留 <relative_path>::<logical_name> 组件 ID；覆盖容器/泛型、@import/re-export、build.zig 两种 addModule 映射、调用/构造器/实例化/类型引用。Zig caller 只接受完整 ID 精确解析；任一 Zig 变化保守全量重解析，非 Zig 增量合并存活缓存。alias-only 指纹、删除清理、block 局部作用域、显式类型初始化调用边均已修复；build.zig 同时作为 build artifact 并提取源码引用；源码发现、CallGraph、watch、CLI、prompt、review、服务识别与 artifact facts 已接入。验证：Zig 专项 21 passed、联合 273 passed、最终全量 1795 passed/2 skipped；ruff、mypy、diff、lock、wheel 构建通过；MCP 契约 121/5 为既有基线；正式 stdio 首次/无变更/单文件/build.zig/artifact/删除收敛通过。backlog 与决策草稿已更新，草稿未确认。本轮未提交、未推送；下一语言候选 Lean 4 不自动展开。

### 2026-11-27 18:36 #d1qq

C2 Lean 4 薄适配已完成：保留 path::logical_name 组件 ID，新增 header scanner、Tree-sitter 引用提取与 import/open/export/private/protected 精确 resolver；六平台 ABI 15 grammar 随包离线分发，Tree-sitter 下限升至 0.25.0。任一 Lean 变化全语言重解析，非 Lean 增量合并存活缓存；import-only 指纹、watch、Git 删除收敛、Lake 服务识别与 artifact facts 均已接入。Lean 专项 103、Lean/watch 最终 113、联合 179、全量 1898 passed/2 skipped；mypy 0 error，ruff/锁文件/diff 检查通过；最终 wheel 六平台 SHA-256 全通过；正式 stdio MCP 首次/无变更/单文件增量通过；MCP 契约维持 121/5 既有基线。决策草稿 repowiki/notes/2026-11-27-lean-analyzer-应按-import-可见域精确解析并离线分发-grammar.md 保持 draft，待用户逐篇确认；下一步仍需用户明确授权提交/推送。

### 2026-11-27 21:24 #ee8z

真实 MCP 复核完成：通过正式 ClientSession/StdioServerParameters 启动 codewiki 5.16.8，握手成功且列出 53 个工具；临时 Git+Lean/Makefile 仓库验证首次 3 组件、无变更 no_changes=true、Point 单文件新增 Geo.jump、Main 单文件增量、list_components/list_dependencies 精确解析到 Geo.jump、Makefile artifact-only 变更及 get_task_context（pending_raw_count=0）均通过。MCP handler 契约仍为 121 passed/5 failed 既有基线。Qoder 宿主连接器状态另经 manage_app_mcp 只读查询：codewiki 当前 disabled、toolCount=0，所以服务端可用不等于宿主工具目录已挂载；未擅自启用或修改连接器配置。

### 2026-11-27 22:24 #p2d6

完成 code-review 修复：语义 manifest（go.mod/pubspec.yaml）变化通过 analyze/watch 共用 helper 失效对应语言全部缓存 caller；go.mod 纳入 mtime/fingerprint，vendor/testdata 嵌套 manifest 不参与指纹。Vue 缓存节点仅复核语言相关边，并用 _parsed_files 保留指向未重解析且仍存在 JS/TS 缓存目标的有效边。Zig 统一 realpath 边界和 canonical 相对 ID，覆盖 build.zig root、import、re-export、declared_in，拒绝绝对/../符号链接逃逸；修正 build.zig 测试素材。验证：八语言+watch 345 passed；相邻分析/缓存 66 passed；清理 NO_PROXY 后全量 1911 passed/2 skipped；ruff/format/diff check 通过；mypy 16 个 cache.py 既有错误；MCP 契约 121 passed/5 failed 既有基线。未提交、未推送。

### 2026-11-28 05:23 #5w2t

已按用户授权提交并推送代码：commit fae7731e8fd428810ee7c7aaf4318f0a24eef3ca（feat: 扩展多语言分析并加固增量缓存），分支 feat/codewiki-upstream-b1-b5-c2-c3，本地与 origin 同步。提交仅含 codewiki/、pyproject.toml、uv.lock 和六个新增语言测试；未纳入文档、repowiki 笔记/任务记忆、telemetry、.qoder/settings.json、work/ 等并行会话产物。全量回归 1911 passed/2 skipped。

### 2026-11-28 05:25 #5126

非代码交付物已按用户授权提交并推送：commit 9ec88b5da362ab7909d0ddea653234b25aa893dc（docs: 归档多语言适配决策与任务记忆），包含 2 份任务文档、8 篇决策/经验草稿和本任务记忆；分支 feat/codewiki-upstream-b1-b5-c2-c3 已与 origin 同步。仍排除 .qoder/settings.json、telemetry、会话 raw、work/、wiki log 与并行用户记忆等运行时/并行会话产物。

### 2026-11-28 05:29 #80ko

2026-11-28 会话：切换到 feat/codewiki-upstream-b1-b5-c2-c3 并拉取最新（HEAD 6e9ada99）。OCR 委托模式审查最近一次提交 6e9ada99（docs: 记录知识资产提交里程碑）：纯文档提交，仅 repowiki/tasks/他山之石/memories/iamwangbao-163-com.md +4 行，OCR 判定 0 可审查代码文件（unsupported_ext 排除）。人工核验：新增记忆条目 #5126 与其引用的 9ec88b5d 提交内容一致（11 文件 +432/-16，含 8 篇决策/经验草稿与任务记忆），分支与 origin 同步，无问题，Approve。

### 2026-09-10

teamai-cli 增量调研完成并存档：基线 docs/teamai-cli-调研与借鉴分析.md（2026-08-21 v0.20.0）→ 现 HEAD 9e7adc7（2026-09-10，v0.23.1/v0.24.0-beta.5），250 个新提交。存档为 docs/teamai-cli-增量调研与借鉴分析-2026-09.md。

两个最值得借鉴的合入：①#374 数据分区——~/.teamai/projects/<slug(anchor)>/，slug=basename+sha256 前 16 hex（8hex 不安全有论证），projectAnchor（worktree list 首项，共享身份）与 workspaceRoot（当前检出，资源落点）分离，明确否决 git-common-dir 方案，锁改 O_EXCL+owner token+回收哨兵；②#336 摩擦信号从 CodeBuddy transcript 确定性提取（interrupt/toolReject/toolError 三类，CodeBuddy 需读 messages/*.json blob，'User rejected this command' 只计人拒，isError 只计真失败），可直接移植补 CodeWiki friction_score 恒为 0 的缺口。次要：#375 role×project 正交+learnings 根层共享子目录私有、#304 WASM tree-sitter 可选降级+PARSE_SKIP gap、#368 KB Health 报告。

下一步待用户拍板：①摩擦信号移植 ②分区+锁 ③先立 ADR；以及是否把可复用机制沉淀为 repowiki note。借用项目统一克隆到 D:\repos 的动作只完成 teamai-cli（其余 20 个未克隆，上次批量克隆命令被取消）。

### 2026-09-10

grill 拷问后拍板 teamai-cli 借鉴处置（判据=只有实测缺口才做，Doctrine 归因调优 SOP）：8 个候选 0 个直接做、7 个 excluded、1 个待实测。

初稿两个判断被证伪：①「friction_score 恒为 0 是缺口」——实际 friction.py 已有打分（correction×20+interrupt×20+repeat×15+规模档，min_user_turns=4），且 [tool-error:] 行已由 tool_digest.py:213-237 写进 raw，只是没计数；②「锁缺 owner token」——store.py:166-189 用 OS flock，比 teamai 的 O_EXCL+owner token+陈旧回收更强（后者是无 flock 的替代品）。

#336 探测结果：repowiki/raw 仅剩 8 条、含 tool-error 的仅 1 条，漏检率 0%（阈值 20%），但该会话 score=5 已被覆盖 → excluded，原因「实测无缺口」；附样本量警告：n=1 不足以证否，复测需 keep_raw 积累或改用 repowiki/tasks 更大样本。

其余 excluded 原因：#374 模型相反（我们知识随仓库版本化 vs 他们机器数据搬出业务仓）+ 身份解析我们用宿主 *_PROJECT_DIR 更靠前；#375 分发维度 vs 归属维度（related≠same）；#304 tree-sitter 我们是主线；#368 无趋势数据；#458/#465 无删除用例；#380 无分发形态。frontmatter 三条转自查 checklist 不立项。

处置表已写入 docs/teamai-cli-增量调研与借鉴分析-2026-09.md §6，§1/§2/§3 的初稿判断已就地加修正。待用户确认是否沉淀 lesson 笔记：借鉴调研前先查本仓是否已有该能力，别把「没宣传」当「没做」。

### 2026-09-11

继续「docs 里借鉴过的项目自上次借鉴后的新合入」调研。先跑全景扫描：11 个本地克隆逐个 git fetch + rev-list --count --since=<各调研文档标注的基线日期> origin/HEAD。增量：codebase-memory-mcp 1182、semantica 682、WeKnora 588、OpenViking 268、llm_wiki 183、claude-mem 36、openwiki 34、RepoWiki 23，MindForge / wikiskill / AIO 均 0。全景表写进 docs/claude-mem-增量调研与借鉴分析-2026-09.md 附 A。

本轮深挖 claude-mem（基线 2026-09-02 f92996e/v13.23.1 → d095021d/v13.24.1，36 commit），产出 docs/claude-mem-增量调研与借鉴分析-2026-09.md，处置：7 候选 0 采纳 / 2 deferred / 5 excluded。两项 deferred：①#3898 tool_uses 的四条工程不变量（upsert ON CONFLICT、自读工具跳过、64KB 截断+原文 content_hash、原始 body 只按 id 取）留档，承接 teamai #336 的 per-call friction 计数；②#3960 skill_invoked 技能遥测——本仓 telemetry 只有 hit/adopted/by_file，无技能维度事件，是真缺口，但技能命中率尚未成为任何在办项判定输入，故 deferred 到 skill_creator 验证阶段。核心证伪：claude-mem 新增能力依托「OpenRouter 计费归因 + 插件市场分发」两个本仓没有的前提。

下一轮队列（已排）：OpenViking（268，#4858 输入过滤 / #4900 跨宿主 turn 捕获 / #4779 队列自愈 / #4906 recall 装配，与采集注入同层，候选密度最高）→ openwiki（34，#859 指纹忽略 Windows ctime 漂移、#777/#841 AGENTS.md 托管块）→ WeKnora（588，文档健康检查）。

### 2026-09-11（续）

本轮连带发现一条会推翻旧结论口径的事实：`[tool-error: …]` 行只由 tool_digest 产生，而它在本仓只有两个调用点（_ide_hook.py:268、capture_conversation.py:221），session-end 的 transcript 补采集（capture_session_end.py）不经过 tool_digest。因此 teamai #336 上次实测「8 条 raw 中仅 1 条含 tool-error、漏检率 0%」测的其实是**通道覆盖面**而非漏检率——复测前必须先回答「工具失败信号在几条通道上被采集、各自覆盖多少会话」，否则加大样本只是放大同样偏差。已写进 docs/claude-mem-增量调研与借鉴分析-2026-09.md §1.3。

顺手做了下轮两项的预检（已落文档附 B）：OpenViking #4724（camelCase isError）→ excluded，数据面不同（本仓走 hook payload 的 is_error，他们修 AI SDK/transcript 的 isError），附前瞻提醒：将来若加 transcript 直读通道必须同时认 isError；openwiki #859（指纹忽略 Windows ctime 漂移）→ excluded，本仓指纹基于内容（doc_similarity.compute_fingerprint:109、page_manifest.compute_source_fingerprint:104），不用 stat 元数据。

下一轮开工点：OpenViking 深挖（基线 2026-08-21，268 commit），候选清单：#4900 跨宿主 turn 协议保留捕获、#4906 从装配 prompt 召回、#4858 recall/capture 的可配置正则输入过滤（对照 _FRAMEWORK_NOISE）、#4779 dsh 队列进程内排空自愈、#4907 缺失任务记录视为已删除（对照 task 索引 stale 条目）、#4559 跳过争用的父级新鲜度更新。

### 2026-09-11（整体报告）

11 个借鉴项目全部完成增量扫描，产出 docs/借鉴项目整体增量调研报告-2026-09.md。合计 44 候选：0 采纳 / 15 deferred / 29 excluded。三路并行采集（OpenViking+openwiki / WeKnora+llm_wiki / CBM+semantica+RepoWiki），本仓对照与裁决由主 Agent 完成，子代理只做事实采集。

三条结论：①一半以上候选本仓早有等价物——最典型是 OpenViking 的 auto-recall 预算机制，本仓 codewiki/mcp/tools/injection_budget.py:1 的 docstring 第一行就写着「V2, OpenViking auto-recall 借鉴」，已落地；另有 deprecated≈墓碑、内容指纹 upsert、多信号确定性排序、git≈修订历史等 6 个样本，坐实「借鉴调研先证伪」那条 stable 笔记。②他仓集体往服务端/队列/多租户走，本仓是本地 markdown + git + 同步 MCP，属主动不同（未知 task_id 显式报错、stale 索引就地跳过）。③真主线是「成本/预算从软约束变硬约束」（CBM 无损分页、WeKnora 砍 LLM 重排、llm_wiki 早停、OpenViking 超预算丢弃、RepoWiki 扫描预算），本仓 injection_budget 在注入侧已就位，空档在扫描侧预算与 deprecated 防重灌。

15 项 deferred 分三类：留档照抄（#1-9）、转其他任务裁决（#10 CBM workspace manifest 审批 → 多仓工作区）、自查项（#13 wikilink 重写代码围栏、#14 ADR 是否整文件重写、#15 deprecated 是否会被新 ingest 复活）。

口径提醒：提交数 rev-list --count（含 merge）与 --no-merges 差异很大（CBM 1182 vs 727），报告里已写明，以后别当矛盾。

### 2026-09-12

HL-Mem 调研（docs/HL-Mem-调研与借鉴分析.md，基线 v1.1.7/aa5d0688）经 grill-with-docs 两轮拷问定稿：16 候选处置不变（4 absorbed / 5 deferred / 7 excluded），但范围收窄：①A1 冲突一等对象——源码实测剥离≈重写（纯函数约 1800 行 + SQLite 绑定约 2200+ 行），自动发现依赖 slot 注册表底座被排除，只做手动声明；定稿顶级 conflicts/ 页面类型（ADR-0007，否决 notes/conflicts/ 与双向引用），已立项任务「冲突一等对象」，排期与 Phase5 批次二错开。②A3 反馈延寿降档并入 Phase5（公式 BayesianUsefulnessPolicy 37 行纯函数可直抄，三层夹紧），任务记忆已转注 Phase5。③A2 能力矩阵落点定 docs/capability-matrix.md（非 repowiki，产品元文档不进知识语料），已编写：首次登记约 20 项，发现 registry 描述 22 vs 实际 24 checks 漂移待修。④A4 三态门控（tri-state gate）已落 CONTEXT.md glossary + CONTRIBUTING.md。⑤C7 降级口径（检索无结果明确回「未检索到」）已落 agents.md 使用建议第 5 条。克隆已归位 D:/repos/hl_mem；Experience 通道已立项「Experience-通道调研」待排期。二次复核修正报告三处事实错误：矩阵实为 7 列 39 条非 4 列 37 条；C8 与 Phase5 T7 的矛盾已补注；补记 service_health 槽位二次夹紧。

### 2026-09-12（存储与压缩机制专题）

六参考项目（hl_mem/claude-mem/mem0/CBM/OpenViking/teamai-cli）存储与压缩机制对比已完成，产出 repowiki/wiki/queries/参考项目记忆存储与压缩机制对比-2026-09.md。要点：①「压缩」四分类（写入时/归纳式/上下文预算/衰减）不可混用；②全场只有 teamai-cli self 模式与本仓一样知识随业务仓 git 版本化；③OpenViking merge_policy 与本仓 Doctrine 合并纪律几乎逐句对应（独立收敛互证）；④HL-Mem Mental Model 归纳 ⇔ compact_task_memories 同一形态。

**重要修正（作废一条转注）**：整体调研报告 deferred #10「CBM workspace manifest 审批键」系误读——CBM 的 workspace manifest 实为 Rust Cargo.toml workspace 清单（跨 crate 导入解析，pass_lsp_cross.c:478-488），与审批/多仓无关。此前转注到「多仓工作区」任务的这条参考已失效，实施多仓工作区时勿再消费该参考。

### 2026-11-28 08:10 #qtf0

2026-11-28 全量测试会话（feat/codewiki-upstream-b1-b5-c2-c3 分支）：
1. 全量 pytest 1902 passed / 12 skipped / 0 failed（Windows 本机），OKF 契约 127/127 全过（基线 121/5，修复 5 个落后断言并新增 2 个）。
2. 修复 6 个分析器 Windows 路径分隔符 bug（rust/vue/zig/lean/javascript/typescript 的 relpath 缺 .replace(os.sep, "/")）+ ast_parser._file_to_module_path 双分隔符替换 + analysis.py 两处 artifact_facts 路径归一化 + artifact_facts_path() 返回正斜杠。
3. 修复升级阻断问题：vendored Lean grammar 的 Linux .so 从未提交（.gitignore *.so 规则静默排除），从 xberg-io/tree-sitter-language-pack v1.14.3 的 parsers-linux-*.tar.zst 提取，sha256 与 provenance.json 完全匹配，已 git add。
4. 修复 safe_write 的 Windows 文件锁问题（os.replace 加 PermissionError 重试）。
5. 测试侧修复：test_vue utf-8 encoding、test_artifact_facts symlink skipif、test_runtime_boundaries 分隔符归一化、OKF 5 个落后断言。
6. prompt_server.py 新增显式 output_dir 定位符支持（修复 get_prompt 不注入 OKF 段的产品缺陷）。
待办：所有改动未提交，等用户醒来 review 后决定 commit 拆分。

### 2026-11-28 12:48 #yoog

2026-11-28 提交推送完成：6 个提交已推到 origin/feat/codewiki-upstream-b1-b5-c2-c3（6e9ada99..145ffa1d）：①69568713 补交 vendored Lean Linux .so（升级阻断修复）；②c28172da 六分析器+ast_parser+analysis/artifact_facts 路径正斜杠归一化；③45d3f2be get_prompt 显式 output_dir 定位符 + safe_write Windows 文件锁重试；④0dcb63cc 测试侧 Windows 兼容修复（编码/symlink/分隔符/OKF 5 断言）；⑤bf88ab04 python.py 补漏；⑥145ffa1d 蒸馏笔记与任务记忆归档。全量 pytest 1902 passed / 0 failed，OKF 127/127。telemetry 与 .codebuddy/memory 按约定未提交。
