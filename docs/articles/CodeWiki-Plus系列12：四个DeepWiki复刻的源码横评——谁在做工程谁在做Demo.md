# CodeWiki-Plus 系列 12：四个 DeepWiki 复刻的源码横评——谁在做工程，谁在做 Demo？

> 上一篇讲了 CodeWiki-Plus 自己怎么回答"机器写的 Wiki 凭什么可信"。这一篇把镜头转向外面。DeepWiki 火了之后，开源圈冒出来一批复刻和同类项目，star 都不低：deepwiki-open 17.9k，openwiki 16.2k，OpenDeepWiki 3.6k，deepwiki-rs 1.7k。我最近做 CodeWiki-Plus 的竞品调研，把这四个项目的源码全部克隆下来通读了一遍，加上 CodeWiki-Plus 自己，五个项目摆在一起对比。先说这篇的立场，也是整次调研最大的收获：**star 数和技术含量是两回事，README 和代码是两回事，"有 Demo"和"有工程"更是两回事。** 下面按源码说话。

---

## 引子：为什么非得读源码

调研方法先交代清楚。四个仓库全部浅克隆，commit 时点从 2026-08-15 到 2026-09-04，四个子代理并行读源码，每一个论断都要求落到`文件:行号`。为什么这么较真？因为这已经是我们踩过的坑：之前调研 claude-mem，文档站说它有 4 个工具，代码里实际 19 个。

这次的教训更生动。下面这张表，左边是 README 的宣称，右边是源码的真相：

| 项目 | README 宣称 | 源码实际 |
|------|------------|----------|
| deepwiki-rs | 支持 Go | 语言处理器就 12 个（rust/js/ts/php/react/vue/svelte/kotlin/python/java/csharp/swift），没有 Go（`language_processors/mod.rs:44-57`） |
| deepwiki-rs | "research agents in parallel" | 并行工具函数全库只用了两处，agent 之间和逐目录总结全是串行 for 循环（`preprocess/mod.rs:146`） |
| deepwiki-rs | `--skip-*` 旗标可跳过阶段 | 三个旗标是死代码，声明了全库没有消费点（`cli.rs:36-44`） |
| deepwiki-rs | 缓存省 token | 缓存条目存了 model_name 字段，读取时却不比对，换模型照样命中旧答案（`cache/mod.rs:88-109`） |
| OpenDeepWiki | "多语言代码分析" | 全库没有任何 AST 或语言解析器，代码理解全靠 LLM 加 ReadFile/ListFiles/Grep 三个工具（`GitTool.cs:770-781`）；所谓多语言，指的是输出文档的多语言 |
| deepwiki-open | LiteLLM 支持 | LiteLLM 只是它自研的 10 个客户端里的一个可选项（`api/clients/litellm.py:8-49`），不是核心抽象 |

一个项目占四行，因为 deepwiki-rs 是重灾区。这不是要踩谁，而是想说一个判断：**这一批项目处在"DeepWiki 概念验证"的窗口期，README 的营销属性大于文档属性。** 你要是想从中借鉴点什么，读代码是唯一可靠的方式。

---

## 一、五个项目，五条路线

先把五个项目的底子摆出来（star 数据取自 2026-09-06 的 GitHub API）：

| 项目 | Stars | 技术栈 | 形态 | 一句话定位 |
|---|---|---|---|---|
| CodeWiki-Plus | — | Python + Vue | MCP 服务端（47 工具） | 本地优先的 LLM Wiki 生成与知识飞轮，嵌在 IDE Agent 工作流里 |
| openwiki | 16.2k | TypeScript + LangChain | npm CLI + 内部 MCP | "自维护 wiki"：planner 到逐页 worker 的 agentic 生成，外加一套事实治理 |
| deepwiki-open | 17.9k | Next.js + Python FastAPI | Web 服务 | Devin DeepWiki 的开源复刻：输个仓库 URL，生成 wiki 加网页问答 |
| OpenDeepWiki | 3.6k | ASP.NET Core + Next.js | 自托管平台 | 多仓库多分支多语言的知识库托管平台，带组织权限和 Admin 后台 |
| deepwiki-rs (Litho) | 1.7k | Rust | 纯 CLI | 一次性的 C4 架构文档生成器 |

几个容易被外表骗到的点，展开说说。

**deepwiki-open 不是 TypeScript 项目。** GitHub 把它的主语言标成 Python，但很多人的印象里它是"那个 Next.js 的 DeepWiki 复刻"。读代码才知道，Next.js 那层只是个反向代理，`src/app/api/*/route.ts` 把请求原样转发给后端；真正的心脏是 Python FastAPI（`api/main.py:50-72`），重度绑定 AdalFlow 框架。一个 Docker 容器里跑两个进程，这是"Demo 长得快"的典型架构：前端抄 DeepWiki 的皮，后端拼 RAG 的架子。

**deepwiki-rs 已经在收缩。** 它的产品名改叫 Litho，README 里明确宣布演进为后继项目 Terrain，Litho 收缩为"快速聚焦的 C4 文档生成器"（README.md:31-40）。主理人的开发重心已经转移。借鉴它的机制之前，得先掂量这个项目还能活多久。

**OpenDeepWiki 是五家里唯一做"平台"的。** ASP.NET Core 单体 + EF Core 双数据库 + 组织/部门/角色权限 + Admin 后台 + IM 接入（飞书/QQ/微信/Slack）。它解决的问题不是"怎么生成好文档"，而是"企业内部的知识库服务怎么运营"——这是另一个问题域。

---

## 二、分水岭之一：谁在做真正的代码分析

这是五个项目最根本的差异，也是我读完之后心里最有底的一件事。

四个竞品，无一例外，全部走"LLM 直接读文件"的路线：

- **openwiki** 是有意为之的架构选择：planner agent 拿着 ls/glob/grep/read_file 四个只读工具在仓库里逛，每页 worker 加上写权限但被限制只能写自己那一页。零 AST，零依赖图，零嵌入向量。它的态度是相信 agent 的泛化能力。
- **OpenDeepWiki** 更极简：LLM 加 ReadFile/ListFiles/Grep 三件套，没了。
- **deepwiki-rs** 表面上有 12 个"语言处理器"，读进去发现是正则和关键词匹配，复杂度统计用 `content.matches("fn ")` 这种字符串计数（`mod.rs:112-143`）。介于"有分析"和"没分析"之间，但更靠近没分析那头。
- **deepwiki-open** 用向量检索替代代码理解：文件按 350 词一块、100 词重叠切开，扔进 FAISS。

而 CodeWiki-Plus 的底座是 Python `ast` 加 tree-sitter 的静态分析管线：组件清单、函数签名、调用图、服务边界检测、跨服务路由匹配，全部来自真实的语法分析。这个差异的后果很直接：**四家竞品的代码事实正确性完全押注在 LLM 身上，代码一重构，文档里的行号引用就漂移；CodeWiki-Plus 的分析图谱本身就是重定位的预言机**——组件搬家了，图谱重分析会给出新位置。

有意思的是，没有一家复刻选择做静态分析。原因不难猜：LLM 读文件这条路，两周就能出 Demo，star 涨得飞快；AST 管线要适配十种语言，半年都不一定讨好。但两条路的长期差距，会随着文档被使用的时间慢慢拉开。

---

## 三、分水岭之二：增量更新，只有一家及格

"代码变了，文档怎么办"，这是所有 wiki 生成器的生死题。答案分布很有意思：

**deepwiki-open：没有。** 这是 star 最高项目最刺眼的短板。它的 wiki 缓存键只有仓库名，不含 commit、不含分支（`pipeline.py:163-167`）；已经克隆过的仓库直接复用旧克隆（`pipeline.py:366-371`）。上游仓库更新之后，它手里的索引和 wiki 全部悄悄过期，唯一的解决办法是手动删缓存重建。更糟的是用户根本不知道过期了。

**deepwiki-rs：也没有。** 每次运行直接删掉整个输出目录全量重写（`outlet/mod.rs:79-82`）。它的 prompt 缓存能省点 LLM 调用费，但流程本身是全量的。

**OpenDeepWiki：有，仓库级。** 定时检查远程 HEAD commit，有差异就建任务，changed files 从 git diff 拿，增量 prompt 里明确禁用整树重写的工具（`WikiGenerator.cs:704-707`）。粒度粗但方向对。

**openwiki：这一题的满分答卷，四层机制。** 第一层，git HEAD 没变就直接 no-op 返回；第二层，对全部文件内容做 sha256 源指纹，运行中源码漂移就不推进 checkpoint；第三层，页级 manifest 记录每页覆盖的文件指纹，没受影响的页直接 fast-forward；第四层，上一篇讲过的 Grounded Claims，每条事实带证据 URI 和内容哈希，update 前先跑 preflight 逐条比对，产出 stale 清单喂给 planner 决定哪些页真正要重写。

四层机制环环相扣，全是为了回答一个问题：**这次更新，到底哪些页需要动？** 相比之下，"每次全量重写"的做法在十页 wiki 上没感觉，在一百页 wiki 上就是灾难。

CodeWiki-Plus 在这一题上的位置，坦白说属于第二梯队上半段：模块页有 commit_id 锚点加 git diff 的受影响模块检测，共享池笔记有页面级 manifest（这两块部分机制正是 8 月底从 openwiki 借鉴落地的）。和 openwiki 的差距在于：我们的 `stale_evidence` 检查结果目前只进 lint 报告，还没有回灌到增量决策里。这个后面说。

---

## 四、分水岭之三：检索与问答的三个极端

这一维度的分布像个光谱，两端都是几万 star 的项目。

**deepwiki-open 站在"有 RAG"的一端**，而且是五家里唯一的向量检索：FAISS，top_k=20，嵌入模型默认 OpenAI text-embedding-3-small。但读细节就会发现这套检索工程上是五家里最弱的：纯单路召回，没有 rerank，没有混合检索，没有查询改写；分块按词数硬切，跨块语义割裂；每次聊天请求都从 pickle 反序列化整个 FAISS 库，大仓库热路径开销可观（`research.py:33-57`）。还有个挺萌的设计：用户输入超过 7500 token 就直接跳过 RAG 裸答。**它有检索，但检索本身不是它的护城河，网页问答的 Demo 体验才是。**

**openwiki 站在"无检索"的另一端。** 全库 grep 不到任何 embedding 或向量代码。它的问答策略是给 agent 一句 prompt："先去 /openwiki 目录里翻 wiki，用 grep 和 glob"，纯靠 agent 拿文件系统工具翻。诚实说，这条路在 wiki 小的时候完全够用，而且省掉了嵌入模型的依赖；wiki 大了之后命中率和 token 成本都会退化。它甚至在 frontmatter 规范里给 description 字段注明"为检索工具优化"，翻译过来就是：**检索这活儿，我留给别人做。**

**OpenDeepWiki 居中但更糙**：没有向量，聊天时把整棵 wiki 目录塞进工具描述里，agent 按行区间去读文档；跨仓库搜索靠关键词打分（`McpGlobalTools.cs:456-464`），不是语义检索。

CodeWiki-Plus 走的是中间路线：BM25 关键词检索，排序里乘了文档权威度和热度，外加一个独有的反馈闭环——**被 Agent 检索后实际采纳的文档，采纳计数会反哺排序权重**。检索质量这个话题，五个项目谁都不敢说做完了，但"检索结果能不能反过来教育检索器"这个钩子，目前只有我们挂上了。

---

## 五、分水岭之四：三种 MCP 哲学

MCP 这维度上，五个项目倒是各自选了三种完全不同的哲学。

**CodeWiki-Plus：MCP 就是本体。** 47 个工具覆盖分析、文档、知识、质量、任务、工作区，整个产品以 stdio MCP 服务端的形态嵌进 IDE Agent 的工作流。这是"工具供 Agent 调用"的哲学。

**openwiki：MCP 是流水线的协议化。** 它的 MCP server 只暴露 6 个工具：begin、submit_plan、next_page、inspect_claims、submit_page、finish。仔细看，这不是能力接口，是把"逐页生成队列"这套流程本身开放给外部宿主——宿主 coding agent 用自己的模型和原生仓库工具做研究和写页，openwiki 管队列、管校验、管收尾。**它把"怎么保证质量"握在自己手里，把"干活"外包给宿主。** 这个分工思路值得细品。

**OpenDeepWiki：MCP 是商业化接口。** 全局和仓库级两个 HTTP 端点，7 个工具，配了 API Key、完整 OAuth 2.1 流程、Protected Resource Metadata、用量统计中间件（`Program.cs:388-392`）。这是把知识库当对外服务来运营的姿势，五家里唯一认真做了"计费基建"的。

deepwiki-open 和 deepwiki-rs：无 MCP。

---

## 六、分水岭之五：对 LLM 的依赖程度

前几条分水岭看的都是"做了什么"，这一条看"靠什么做"。整个管线里确定性代码和 LLM 的配比，决定了两个东西：**成本曲线和正确率上限。**

**OpenDeepWiki 是五家里最重的。** 数一下 LLM 出场的次数：目录生成是一次 agentic 调用（agent 拿着目录树和 README 用 `WriteCatalog` 写 JSON）；每篇文档又是独立 agentic 调用，带着完整系统提示词和工具往返；多语言靠 LLM 逐篇翻译已有文档（`TranslateWikiAsync`），不是复用分析结果。整条管线没有一处确定性的代码理解托底，"目录模型"和"内容模型"分开配置已经是它对成本的全部思考。

**deepwiki-open 是三次出场加一个影子。** 结构 XML 一次、逐页生成一次、网页问答一次，外加一个常驻的嵌入模型——连"哪段代码和这个问题相关"都要模型说了算。确定性部分只有文件树展示和文本分块。它的省钱努力体现在防御性解析（被截断的输出抢救出来重用）而不是减少调用。

**deepwiki-rs 有个确定性骨架。** 目录扫描、文件重要性打分、正则语言处理都不花 token，这是它值得肯定的部分。但从逐目录 LLM 总结开始（`preprocess/mod.rs` 的 DirectoryDossier），7 个 research agent、6 个 compose editor 就全是 LLM 了，骨架之上全是模型。

**openwiki 全是 agent，但有分寸感。** planner 和 worker 都是完整 agent，分析零静态底座，按说是最重的一家——但它在收尾处把机械活从 LLM 手里拿了回来：finalizer 纯代码、index.md 禁止模型手写。它对 LLM 的态度是"干活可以，签字不行"。

**CodeWiki-Plus 的配比最克制。** 分析阶段零 LLM：组件、签名、调用图、行区间全部来自 AST 和 tree-sitter 的语法分析，这一段一个 token 都不花。生成阶段 LLM 只当翻译官——事实是分析器采出来的，模型只负责说清楚；上一篇讲过的置信度协议再补一道闸：没有代码证据的断言必须挂牌 `[candidate]`。**依赖度低的直接回报是：代码事实的正确性不随模型发挥波动。**

---

## 七、分水岭之六：团队经验沉淀与任务记忆

这一条是横评里最一边倒的维度。问题是：**用这个工具一个月之后，团队比一个月之前多了什么？**

**deepwiki-open：什么都不多。** 对话历史由前端每次全量携带，后端在内存里重建对话对象，服务重启即失（`research.py:107-116`）。连单人使用者的连续性都没有，更谈不上团队。wiki 缓存是一次性产物，没有回流机制。

**OpenDeepWiki：有组织，没沉淀。** 它的组织/部门/角色体系做得很全，但那是访问控制，回答的是"谁能看"，不是"谁知道"。聊天记录进 ChatLog 是审计日志，不是可检索的知识。多人共用一个 wiki 站，各自的理解并不会因此累积。

**openwiki：治理单篇事实，不沉淀团队经验。** Claims 账本管的是"这篇文档里每条断言是否仍有证据"，这是文档级事实治理；团队踩过的坑、做过的决策、推翻过的方案，没有对应的容器。它的 personal 模式有 9 类连接器（Slack、Gmail、HackerNews……）能摄取个人数据流，但那是个人知识库方向，与代码 wiki 主线正交。聊天会话有 SQLite checkpointer 持久化，但那是会话状态，关掉就是历史。

**deepwiki-rs：最接近的一个，但只做了一半。** 它的 `.ai-context/` 分层知识库（Tier0 项目本质 → Tier3 当前问题）按稳定性组织知识供 coding agent 消费，"AGENTS.md 讲怎么干活，.ai-context 讲项目是什么"这个分工是对的。但内容是一次性生成的，用完即弃，没有从使用中回流的通道——是个静态的说明书，不是飞轮。

**CodeWiki-Plus 在这条线上没有对手：对话捕获 → 蒸馏 → 草稿笔记 → 确认闸门 → 采纳计数反哺检索排序，外加 Doctrine 团队共识和跨会话的任务记忆（分片存储、多人隔离）。** 工具越用，库里的确认笔记越多，检索排序越准，团队的决策脉络越完整。这是"Wiki 生成器"和"知识系统"的分界线：前者生成完就结束了，后者从使用中变厚。

不过没有对手不等于做完了。沉淀的另一半是治理成本：确认闸门需要人过目，笔记多了需要合并退役，这些成本是真实存在的。四家竞品没做这件事，可能不是没想到，而是不想让用户背这个成本。CodeWiki-Plus 的判断是值得背——但这个判断本身，也需要用飞轮里的使用数据持续检验。

---

## 八、每家压箱底的工程亮点

横评不能光挑刺。四个项目各有几处设计，读的时候让我停下来记了笔记。

**openwiki 的确定性收尾。** 每次生成或更新结束，跑一段纯代码的收尾流水线：mermaid 校验、索引同步、内链校验、Claims 投影、provenance 盖章，一步 LLM 都不掺和；目录的 index.md 由代码生成，明令禁止模型手写（`wiki-finalizer.ts:248-285`）。这个分寸感很高级：**LLM 负责写内容，机械的活儿交给机械。** 顺便，它的页队列持久化在 `.run.json` 里，CI 上跑挂了，重跑就从断点继续。

**deepwiki-open 的防御性解析和并发闸门。** 它对 LLM 输出的解析健壮得有点夸张：XML 被截断就用手写状态机从残缺 JSON 里抢救出已完整的对象，零额外 LLM 调用（`structure.py:179-250`）——明显是被小本地模型折磨出来的。并发控制是三层信号量：RAG 索引 4 并发、任务池 CPU 核数一半、页级默认 1，各自独立可配。还有 SSE 心跳的细节：每 10 秒发一个注释帧，就为了躲 undici 默认 300 秒的 headers 超时，索引任务用 `asyncio.shield` 罩着，心跳超时也不会误杀（`repo.py:20-57`）。工程上全是脏活，但没有这些脏活 Demo 就会随机挂。

**OpenDeepWiki 的单体内分布式调度。** 这是我觉得它最值得抄的一处：DB 租约表加全局槽位加心跳加崩溃恢复，在单体应用里实现了"每仓库单写者、集群总并发上限"（`WikiGenerationConcurrencyService.cs:37-64`）。没有引入消息队列，成本控制得很好。它的断点续跑也实在：已落盘的文档路径直接跳过，单篇失败不中断批次。

**deepwiki-rs 的声明式流水线和双模型。** 它的 StepForwardAgent trait 是个漂亮抽象：每个 agent 声明自己需要哪些数据源（内存键、上游结果、外部知识）、prompt 模板、调用模式，框架自动完成数据校验、prompt 组装、结果写回，新 agent 只写配置不写流程（`step_forward_agent.rs:581-726`）。双模型设计也聪明：主力模型失败时，把错误信息注入 prompt 换备用模型重试，外层套指数退避（`llm/client/mod.rs:106-118`）。另外它的 prompt 哈希文件缓存带 token 用量统计和命中率监控，是省钱的实在功夫。

---

## 九、CodeWiki-Plus 学到了什么

调研的落点不是写文章，是改进自己。排除 8 月底已经从 openwiki 借鉴落地的五项（证据哈希、页面 manifest、mermaid 降级、no-op 防扰、评测框架），这次从四个项目里提炼出的清单，按优先级排三件：

**第一件，LLM 调用缓存加 token 统计。** 学 deepwiki-rs 的 prompt 文件缓存，但要避开它的坑：缓存键必须校验模型名，否则换模型命中旧答案。而且实现前先核对了自己的代码：CodeWiki-Plus 的模块生成是 agentic 多轮调用（agent 带工具走完整轨迹），单次 prompt→response 的缓存根本套不上，能做的只有模块级指纹缓存——输入没变就跳过整个 agent run。教训：借鉴别家机制前，先确认人家的机制对应自己哪段代码，调研报告说的痛点可能自家早就解决了一半。

**第二件，stale_evidence 回灌增量决策。** 这是对已落地机制的"最后一公里"。openwiki 的做法是 Claims preflight 的 stale 清单直接喂给 planner，成为"哪些页要重写"的决策输入。这一件在本文写作当天已经落地：漂移信号成为增量决策的第三信号源，与受影响模块、过期页面并列；代码没变的短路路径保持静默，是有意的不对称——代码没动，工具就不该多嘴。

**第三件，确定性收尾管线。** 学 openwiki 的 finalizer：生成流程末尾加一段纯代码收尾，把索引同步和内链校验从"检查"升级成"检查加修复"。核对代码后范围收窄：真实缺口只剩 generate_docs 这条链路跑完没有任何索引收尾，两处既有调用点已经在了。半天能补完的活。

还有一条产品层面的观察，不是技术决策：deepwiki-open 用五家里最粗糙的工程拿了最高的 star，17.9k。它证明了**网页 Demo 的传播力可以碾压工程质量**。CodeWiki-Plus 目前只有 IDE 侧的消费入口，如果哪天需要传播性，把现有 Vue 前端包装成只读可视化站点，比补齐任何技术短板都划算。这是留给未来的选择题。

---

## 结尾：自己的路线，扒完别人家的源码才敢确认

把五个项目读完整理完，最大的收获不是那三件待办，而是一次定位确认：

**精确代码分析这条路，五家里只有 CodeWiki-Plus 在走。** 四个竞品全部押注 LLM 直读，说明这条路的短期成本优势确实明显；但也说明，AST 调用图这个我们从第一天起就当作理所当然的底座，在同类项目里居然是稀缺资产。

**知识治理这条线，五家里只有 CodeWiki-Plus 和 openwiki 在认真做。** openwiki 用证据哈希把"文档过时"变成可机械验证的状态机；CodeWiki-Plus 在此之外还多压了一层确认闸门和采纳反馈，让知识质量变成有人负责的资产。而剩下三家，连增量更新都没有，谈治理为时尚早。

star 会涨会跌，README 会更新会过时，源码不会说谎。这次调研把四个项目的源码摊开之后，CodeWiki-Plus 该坚持什么、该补什么、该忽略什么，答案都比之前清晰了一层。

---

*（本文基于 docs/DeepWiki类开源项目对比调研报告-2026-09.md 及四份源码调研笔记（.research-competitors/notes/）撰写，全部代码事实经二次核查与源码一致；star 数据取自 2026-09-06 GitHub API。系列前文见 docs/articles/。）*
