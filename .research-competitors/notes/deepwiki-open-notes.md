# deepwiki-open（AsyncFuncAI/deepwiki-open）调研笔记

> 调研对象：本地克隆 `D:\repos\CodeWiki-CN\.research-competitors\deepwiki-open`，commit 时点代码为准。
> 定位：Devin DeepWiki 的开源复刻（README 自称 "my own implementation attempt of DeepWiki"），输入 GitHub/GitLab/Bitbucket 仓库 URL，自动生成 wiki + 代码问答。

## 1. 整体架构与定位

**双进程 Web 服务**：Next.js 15 前端（`src/`，React 18 + tailwind，next-intl 多语言）+ **Python FastAPI 后端**（`api/main.py:50-72`，uvicorn 端口 8001）。注意：这不是纯 TypeScript 项目——核心逻辑（RAG、wiki 生成、聊天流）全在 Python 侧，`api/` 有独立的 `pyproject.toml`/`poetry.lock`。

- 前端 `src/app/api/*/route.ts` 只是**反向代理**，把请求转发到 `SERVER_BASE_URL`（默认 `http://localhost:8001`），如 `src/app/api/chat/stream/route.ts:5,18`（逐字节 pipe SSE 流）。
- 单容器部署：Dockerfile 在一个镜像里同时跑 FastAPI 和 Next.js standalone（`Dockerfile:99-103` start.sh 后台起两个进程）；docker-compose 挂载 `~/.adalflow` 持久化仓库克隆和向量库（`docker-compose.yml:17-18`）。
- 后端路由：system/auth/repo/wiki/chat/codemap 六组（`api/main.py:64-72`）。聊天走 WebSocket `/ws/chat`（`api/routers/chat.py:20-66`），HTTP SSE `/chat/completions/stream` 为回退（chat.py:69-116）；codemap 走 `/ws/codemap` NDJSON（`api/routers/codemap.py:14-49`）。
- 核心依赖 **AdalFlow**（`api/rag/rag.py:7`，adalflow 的 Embedder/LocalDB/FAISSRetriever/TextSplitter 全家桶）。
- 访问控制极简：可选的静态授权码 `DEEPWIKI_AUTH_MODE`/`DEEPWIKI_AUTH_CODE`（`api/config.py:60-62`，`api/routers/auth.py:17-22`），无用户体系、无数据库。

## 2. 代码分析阶段

- **抓取方式是本地 git clone，不是 GitHub API**：`Repo.download()` 用 GitPython 浅克隆 `--depth=1 --single-branch`（`api/repository.py:191-216`），支持 github/gitlab/bitbucket 三种 token 认证格式（repository.py:38-118），也支持本地路径仓库（`is_local`，repository.py:170-171）。
- **不使用 GitHub Embeddings API**（全代码 grep 无 `api.github`/embeddings API 调用）。嵌入自建：读文件 → TextSplitter 分块 → ToEmbeddings 批量嵌入 → adalflow LocalDB pickle 持久化（`api/rag/pipeline.py:248-275`）。
- 文件筛选：配置化 code/doc 扩展名白名单 + excluded/included dirs/files，RAG 索引与文件树展示共用同一实现 `iterate_files`（`api/config.py:467-516`）。超大文件跳过（token > 8192×10，`api/rag/pipeline.py:21,126-129`）。
- 无 AST/依赖图等代码理解——纯文本文件树 + README + 向量检索（见 §4）。meta_data 记录 `is_code`/`is_implementation`（pipeline.py:144-154）但只用于展示，检索时不区分。

## 3. 文档生成流程

异步任务状态机（后端原版是从前端 page.tsx 移植到 Python，见 `api/services/wiki/tasks.py:316` 注释）：

1. **提交任务** `POST /wiki/tasks`（`api/routers/wiki.py:218-228`）：get-or-create 语义——活动任务去重 join、已有缓存直接 `from_cache`（`api/services/wiki/tasks.py:161-190`）。
2. **INDEXING**：仅当 `{repo_name}.pkl` 不存在才建索引（tasks.py:219-222）。
3. **DETERMINING_STRUCTURE**：读本地克隆的文件树+README（`api/services/wiki/structure.py:20-48`），用 LLM 生成 XML 格式的 wiki 结构（sections + pages，每页含 title/importance/relevant_files/related_pages），`build_structure_prompt`（`api/services/wiki/prompts.py:213-260`）要求 4-6 页（concise）或 8-12 页（comprehensive）。XML 解析非常防御性：剥 markdown fence、修 bare `&`、截断抢救、正则 fallback（structure.py:179-250）。
4. **GENERATING**：逐页生成，prompt 为 `build_page_prompt`（prompts.py:25-132）——强制首行 `<details>` 溯源文件块、大量 Mermaid 图、表格、`Sources: [path:line]()` 空括号引用格式（≥5 个文件）。每页生成**复用 RAG 聊天管线**（`_generate_page` 构造 ChatCompletionRequest 走 `research_chat`，tasks.py:369-404），即页面内容由向量检索到的代码块驱动。有界并发 + 每页 2 次重试 + 失败占位页不炸整个任务（tasks.py:268-312）。
5. **缓存**：完成后整包写入 `~/.adalflow/wikicache/deepwiki_cache_{type}_{owner}_{repo}_{lang}.json`（`api/services/wiki/io.py:21-29,52-72`），**缓存键无 commit hash、无过期**。支持导出 Markdown/JSON（`POST /export/wiki`，io.py:146-235）。
6. 进度推送：SSE `/wiki/tasks/{id}/stream`，1 秒轮询 registry 输出 progress/done/error 事件（`api/routers/wiki.py:271-302`）。
7. **后处理**：`post_process_wiki_content` 把模型输出的空括号引用 `[path:line]()` 解析成 GitHub/GitLab/Bitbucket 真实带行锚链接（`api/services/wiki/content.py:84-151`）。

## 4. 检索/问答能力

- **RAG 链路**：adalflow `FAISSRetriever`，top_k=20（`api/config/embedder.json:33-35`），**无 rerank、无混合检索、无 query 改写**。检索结果按文件分组、块标注 `[lines A-B]` 行号注入上下文（`api/services/research.py:157-192`）。
- **嵌入模型**：默认 OpenAI `text-embedding-3-small`（dimensions=256，embedder.json:2-10），可换 Ollama `nomic-embed-text`、Google `gemini-embedding-001`、Bedrock Titan v2（embedder.json:11-32）；类型由 `DEEPWIKI_EMBEDDER_TYPE` 环境变量选择（config.py:65）。分块：word 级 chunk_size=350 / overlap=100（embedder.json:36-40）；`LineTrackingTextSplitter` 为每个 chunk 回写起止行号（pipeline.py:174-208）。
- **向量库**：FAISS + adalflow LocalDB，pickle 文件落盘（`api/rag/rag.py:290-296`，pipeline.py:163-171）。嵌入维度不一致时按多数派过滤（rag.py:183-236）。
- **流式问答**：WebSocket 优先，断线/不可用回退 HTTP SSE（前端 `src/utils/websocketClient.ts` + `src/app/api/chat/stream/route.ts:16`）。
- **Follow-up**：无服务端会话——前端每次带全量 messages，后端把历史 user/assistant 对灌进内存 `Memory`（`api/services/research.py:107-116`），以 `<turn>` 文本拼接进 prompt（research.py:252-259，`api/chat/_prompts.py:13-31`）。对话状态每次请求重建，重启即失。
- **Deep Research 模式**：`mode=deep_research` 时前端自动循环发 "Continue the research"（`src/components/Ask.tsx:392-441`），后端按 `research_iteration` 换三套 prompt（首迭代出研究计划/中间迭代出增量发现/第 5 轮出最终结论，`api/prompts.py:60-151` + `api/services/research.py:214-242`）；迭代由**前端驱动**，后端无状态。
- **Codemap**：两段式 LLM 调用生成"带引用的分步指南"（skeleton JSON → enrich 补 prose+mermaid），JSON 解析带 3 次重试 + 修复（`api/services/codemap.py:39-126`，prompts 见 `api/prompts.py:195-265`）。
- 输入超 7500 token 时跳过 RAG 直接裸答（research.py:23,63-73,147）；超限报错时自动降级为无上下文 prompt 重试（research.py:261-288）。

## 5. 多语言 / 多提供商

- **LLM 提供商**：自研客户端注册表而非引入 LiteLLM SDK——`api/clients/` 下 10 个客户端（google/openai/openrouter/ollama/bedrock/azure/dashscope/anthropic-bedrock 等，`api/config.py:71-95`），`ChatStreamer` 按 provider 名注册子类（`api/chat/_stream.py:29-48`）。**LiteLLM 是其中一个可选 provider**：`LiteLLMClient` 继承 adalflow OpenAIClient 指向 LiteLLM proxy 的 OpenAI 兼容端点（`api/clients/litellm.py:8-49`，配套 docker-compose-litellm.yml/litellm-config.yml）。默认 provider 为 google gemini-2.5-flash（`api/config/generator.json:2-3`）。
- **多语言**：UI 层 next-intl 10 种语言（`src/messages/*.json`）；wiki 内容靠 **prompt 内嵌语言指令**生成（`api/services/wiki/prompts.py:126` "Generate the content in {language}"），**每种语言独立缓存文件独立生成**（io.py:26-29），即中文 wiki = 重新跑一遍完整 pipeline，无翻译管线。问答侧靠"跟随用户 query 语言"的 prompt 指令（`api/prompts.py:8-11`）。

## 6. 值得注意的工程设计

- **并发控制三层信号量**：RAG 索引准备 `DEEPWIKI_MAX_CONCURRENT_RAG=4`（`api/rag/rag.py:27-34`，`asyncio.to_thread` 包同步阻塞操作，rag.py:344-354）；wiki 任务池 `DEEPWIKI_MAX_CONCURRENT_WIKI_TASKS`（默认 CPU/2，tasks.py:62-64）；单任务页级并发 `DEEPWIKI_WIKI_PAGE_CONCURRENCY`（默认 1，tasks.py:66）。
- **SSE 心跳防代理超时**：`/repo/prepare` 每 10s 发心跳注释帧，注释明说为了躲 undici 300s headers timeout；先 flush 首字节再跑慢索引、`asyncio.shield` 保证心跳超时不误杀索引任务（`api/routers/repo.py:20-57`）；配套前端预热器把冷索引从首个聊天请求剥离（`src/utils/prepareRepo.ts:1-9`）。
- **任务生命周期**：终端态任务 TTL 300s 自动出注册表（tasks.py:70,200-206）；get-or-create 幂等提交（tasks.py:161-190）。
- **健壮的 LLM 输出解析**：XML 截断抢救 + 双正则 fallback（structure.py:179-250）、JSON 平衡括号提取 + 修复 + 重试（codemap.py:47-126）、流式 token 超限降级重试（research.py:261-288）——明显是为小本地模型（qwen3:1.7b 是 ollama 默认，generator.json:117）调校的。
- 测试 21 个 pytest 文件（tests/backend 分 routers/services/schemas/rag），在同类项目中算少而精。

## 7. 明显短板 / 局限

1. **无增量更新**：缓存键只有 repo 名不含 commit/branch（`api/rag/pipeline.py:163-167`，io.py:26-29）；已克隆仓库直接复用旧克隆（pipeline.py:366-371），上游更新后 wiki/索引全部 stale，只能手动删缓存重建。
2. **纯 Web 形态，无 MCP/API 优先的消费方式**：全代码无 MCP（grep 零命中）；产出只进私有 JSON 缓存 + 前端渲染 + 手动导出 md/json，不回写仓库、无 PR/CI 集成。
3. **无持久化用户/会话层**：对话记忆在请求内存对象里（research.py:107-116），无多用户隔离；"auth" 只是单个全局授权码（auth.py:17-22）。
4. **检索质量上限低**：纯 FAISS 向量单路召回 top_k=20，无 rerank/混合检索/结构感知分块（embedder.json:33-40）；代码块按词数切分，跨块语义割裂。
5. **RAG 对象每次请求重建**：`research_chat` 每次聊天请求都重新 `RAG()` + `aprepare_retriever`（research.py:33-57）——从 pickle 反序列化整个 FAISS 库，大仓库热路径开销可观，无进程内 LRU。
6. **每语言全量重生成**（§5）、**嵌入维度写死过滤逻辑**（rag.py:183-236 是补丁式容错而非根因修复）、单机单实例架构（TaskRegistry 是模块级内存对象 tasks.py:209，无法水平扩展）。

## 与对比报告相关的关键事实速查

| 维度 | deepwiki-open |
|---|---|
| 形态 | Next.js 前端 + FastAPI 后端，单 Docker 容器，无 MCP |
| 仓库获取 | git 浅克隆（GitPython），非 API |
| 嵌入 | OpenAI text-embedding-3-small(256d) / Ollama / Google / Bedrock 可切换 |
| 向量库 | FAISS + LocalDB pickle |
| 生成管线 | LLM 出 XML 结构 → 逐页 RAG 生成 → 引用后处理 → JSON 缓存 |
| rerank | 无 |
| 增量更新 | 无 |
| LLM 抽象 | 自研 10 客户端注册表，LiteLLM 为可选 provider |
| 多语言 | prompt 指令 + 每语言独立缓存，无翻译管线 |
