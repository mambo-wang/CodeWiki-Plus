# Entity/Concept 提取优化方案（借鉴 WeKnora）

> 日期：2026-08-03
> 参考实现：[Tencent/WeKnora](https://github.com/Tencent/WeKnora) `internal/agent/prompts_wiki.go` + `internal/application/service/wiki_ingest*.go`
> 状态：P0 已实施并验证（2026-08-03，冒烟 94/94、OKF 回归 67/67 通过）；P1/P2 待评审

## 1. 背景与现状

CodeWiki-CN 的 entity/concept 提取目前是**单轮 LLM 一步到位**：

```
ingest_source（整文件存储 + SHA-256 去重）
  → _prompt_extract_knowledge 编排（prompts.py L78-129）
  → LLM 通读全文，自行判断 entity/concept
  → 逐个 write_doc_file(page_type="entity"/"concept") 写完整页面
```

准确性保障全部是**事后质检**：OKF frontmatter 校验、lint 断链/孤立页检测、draft→stable 生命周期。提取过程本身没有任何防幻觉、防误并、防漏提机制。

### WeKnora 的做法（多阶段 Map-Reduce 流水线）

| 阶段 | Prompt | 职责 |
|------|--------|------|
| Pass 0 | `WikiCandidateSlugPrompt` | 只提取轻量骨架（name/slug/aliases/一句话描述），不写完整事实 |
| 去重 | `WikiDeduplicationPrompt` | pg_trgm 预筛 + LLM 精确判断，大量正反例，核心原则"related ≠ same" |
| Pass 1..N | `WikiChunkCitationPrompt` | 对每个候选 slug，判定哪些原文 chunk **实质性讨论**了它，返回 chunk ID |
| 组装 | `WikiPageModifyPrompt` | LLM 当"编译器"而非"作者"：逐字引用原文 chunk，禁止改写措辞和修辞填充 |
| 分类 | `WikiTaxonomyPlanPrompt` | 批量规划目录归属，复用已有文件夹 |

核心思想：**识别与举证分离**。骨架提取便宜且不易幻觉；页面内容由原文 chunk 逐字引用支撑，而不是 LLM paraphrase。

## 2. 差距分析

| 能力 | CodeWiki-CN 现状 | WeKnora | 差距 |
|------|-----------------|---------|------|
| 提取粒度控制 | ✅ 已有（extraction_scan 支持 focused/standard/exhaustive） | ✅ 三档 | 无差距，但 extract-knowledge 工作流未透传 granularity |
| 行级溯源约定 | ✅ 已有（`[^src:name:a-b]` 脚注 → frontmatter chunk_refs） | ✅ chunk ID 引用 | 约定已有，但**无人验证**行范围真实性和内容相关性 |
| 两阶段提取 | ❌ 单轮识别+撰写一体 | ✅ 骨架→举证 | 大差距 |
| 语义去重 | ❌ 仅 slug 碰撞追加 hash | ✅ trigram 预筛 + LLM 判断 | 大差距 |
| 内容防幻觉 | ❌ LLM paraphrase | ✅ 逐字 chunk 引用 | 大差距 |
| 分块基础设施 | ❌ 无（BM25 整文件粒度） | ✅ chunk 存储 + 批次引用 | 大差距 |
| 目录分类 | ⚠️ 有 taxonomy_plan prompt 但未进 extract 流程 | ✅ 批量规划 | 小差距 |

### 已确认可直接复用的存量资产

- `source_ingest.py`：raw/sources/ 存储 + source_registry.json（含 content_hash，可做 chunk 版本对齐）
- `doc_writer.py` L31 `_SOURCE_REF_PATTERN`：已自动从正文解析 `[^src:name:a-b]` 写入 source_refs/chunk_refs——**溯源管道已通，缺的只是"让引用真实存在"**（2026-08-03 e2e 发现并修复两处：①原正则强制 `a-b` 范围，单行引用 `[^src:name:59]` 不被解析，已放宽为 `\d+(?:-\d+)?`；②sessionless 写入路径 `_inject_lightweight_frontmatter` 完全缺失 source_refs/chunk_refs/sources 提取——而 extract-knowledge 无 session 流程恰走此路径，已对齐有 session 路径补齐）
- `query_wiki`：支持 scope/type_filter，可直接当去重预筛用
- `extraction_scan` prompt：已有 granularity 参数和 JSON 骨架输出格式——**这就是 Pass 0 的雏形**

## 3. 设计原则

1. **Prompt 协议优先**：能用 get_prompt + AGENTS.md 约定解决的不加 MCP 端点（项目既定理念）
2. **复用既有约定**：沿用 `[^src:name:a-b]` 行范围脚注作为"chunk ID"（比 WeKnora 的 c001/c002 更可读，且已接入 frontmatter 管道）
3. **Agent-in-loop 适配**：WeKnora 是服务端自动编排（Go 并发），CodeWiki-CN 是 Agent 调用工具——把服务端编排翻译成工作流 prompt 步骤，不照搬 Map-Reduce 代码结构
4. **不引入新依赖**：不学 pg_trgm（CodeWiki 无 PG），去重预筛用现有 BM25/jieba
5. **分三期，P0 纯 prompt 零代码**

## 4. P0：Prompt 协议增强（纯 prompt，约 0.5-1 天）

### 4.1 重写 `_prompt_extract_knowledge` 为两阶段流程

改动点：`codewiki/mcp/prompts.py` L78-129。

新流程骨架：

```
步骤 1: ingest_source（不变）
步骤 2: get_prompt(extraction_scan, variables={granularity}) → JSON 骨架
        【新增约束】骨架阶段只产出 title/type/summary/aliases/source_ref，
        禁止直接写页面正文
步骤 3: 【新增】去重检查：对每个骨架项调用
        query_wiki(query="<title+aliases>", scope="entities"/"concepts")
        → 调用 get_prompt(extraction_dedup) 获取判定规则
        → 输出三分类：新建 / 合并到已有页面 / 丢弃
步骤 4: 【新增】举证校验：重读源文件带行号，逐项确认 source_ref
        行范围内确实实质性讨论了该项（≥2 句或独立段落），
        一次性提及的降级或丢弃（按 granularity 规则）
步骤 5: 逐页撰写：新建→write_doc_file；合并→edit_doc_file 追加
        （模板注入编译器纪律，见 4.3）
步骤 6: 质检（不变，lint + close_session）
```

### 4.2 新增 `extraction_dedup` prompt 类型

改动点：`prompt_server.py`，在 extraction_scan 分支后新增。内容移植 WeKnora `WikiDeduplicationPrompt` 的判定规则并本地化：

- 合并三条件：同一真实事物 + 名称变体（缩写/全称/翻译）+ 类型兼容（entity 只并 entity）
- 正例：Acme Corp ↔ Acme Corporation、RAG ↔ Retrieval-Augmented Generation、苹果公司 ↔ Apple Inc.
- 反例（重点，直接移植 WeKnora 的中文反例库）：混元 ≠ 通义、iPhone 15 ≠ Mate 60、GPT-4 ≠ GPT-3.5、居民身份证 ≠ 工作居住证、学位证 ≠ 毕业证、机器学习 ≠ 神经网络（子集关系不合并）
- 核心原则一句话："**related ≠ same**。拿不准就不合并——宁可两个页面，不可错误合并"
- 输出格式：每个骨架项标注 `action: create | merge | drop` + `merge_target`

### 4.3 页面模板注入"编译器纪律"

改动点：`prompt_server.py` 的 entity_page（L877）、concept_page（L901）、source_summary（L925）模板，追加规则段（移植自 WeKnora `WikiPageModifyPrompt`）：

- **贴近原文**：事实性陈述优先直接引用源文档原句并标注 `[^src:name:a-b]`；可以轻排序、去重、连接，但不得为风格改写、不得把短句扩写成长句
- **禁止修辞填充**："旨在帮助…"、"该平台致力于…"、"具有重要意义"等套话不得出现，除非原文就有
- **范围纪律**：页面每个陈述必须关于页面标题本身；新信息与标题不符时（如页面是"混元模型"但材料在讲"通义"）拒绝采纳
- **不过度结构化**：源文是平铺文本就保持平铺，不为凑章节发明标题层级
- **无引用不成立**：每个事实段落至少挂一个 `[^src:...]` 脚注；写不出引用就说明骨架项证据不足，应丢弃该项

### 4.4 granularity 透传

改动点：`_prompt_extract_knowledge` 增加 `granularity` 参数（PromptArgument），传入 `get_prompt(extraction_scan, variables={granularity})`；默认值从 schema.yaml 的 `extraction_granularity` 读（prompt_server.py L94-97 已有注入逻辑，补一行取值即可）。

### P0 effort/benefit

- 工作量：约 4-6 小时（全部是 prompt 文本改动 + registry.py 加一个 PromptArgument）
- 收益：两阶段分离后骨架提取不再被"写全文"拖累，漏提率下降；去重正反例直接消除同类误并；编译器纪律 + 强制引用消除大部分 paraphrase 幻觉
- 风险：零（不改任何数据结构和工具签名）

## 5. P1：轻量代码支撑（约 1.5-2 天）

P0 靠 Agent 自觉，P1 加机械保障。

### 5.1 源文档分块器

新增 `codewiki/src/chunker.py`（约 150 行）：

- Markdown 源：按 `##` 标题边界切块，块内保留行号区间；超长块（>1200 字符）按段落二次切
- 非 Markdown 源：段落切块，size 上限对齐项目 RAG 约定（800 字符，overlap 50）
- 产物存 `.meta/source_chunks.json`：

```json
{
  "<source_name>": {
    "content_hash": "sha256:...",
    "chunks": [
      {"id": "c001", "start": 12, "end": 45, "heading": "## 架构", "text": "..."}
    ]
  }
}
```

- 触发点：`handle_ingest_source` 成功后自动生成；content_hash 变化时重建（registry 已有该字段，天然支持增量）
- chunk 的 start/end 与 `[^src:name:a-b]` 行范围约定完全对齐——引用即 chunk 定位

### 5.2 引用真实性校验（lint 新 check）

改动点：`wiki_lint.py` 新增 `cite_refs` check：

1. 扫描 entity/concept/source 页面的所有 `[^src:name:a-b]`
2. 校验一（存在性）：source 在 registry 中存在且 status=active；a-b 在文件行数范围内——不满足报 **error**
3. 校验二（相关性，弱校验）：取 source_chunks.json 中覆盖该区间的 chunk text，检查页面标题或 aliases 至少一个出现在 chunk 中，或 chunk 与页面正文 token 重叠率 ≥ 阈值（如 15%）——不满足报 **warning**
4. 校验三（孤儿引用）：frontmatter source_refs 中的 source 已 retracted——报 warning

这步把"引用是否真实"从 Agent 自觉变成机器可查，是 P0 强制引用规则的兜底。

### 5.3 去重预筛提效（可选，约 0.5 天）

骨架项逐个 query_wiki 在实体多时偏慢。可加轻量辅助函数（不加 MCP 端点）：

- `wiki_search.py` 新增 `find_similar_pages(names, aliases, scope)`：对每个名称/别名跑一次 BM25，合并 top-K 候选，返回给调用方
- 暴露方式：挂到现有 `query_wiki` 的 `expand_terms` 同类机制下，或仅作为 lint/内部工具使用——**倾向不加新端点**，P0 的逐个 query_wiki 已够用，此项列为可选

### P1 effort/benefit

- 工作量：chunker 约 0.5 天，cite_refs 约 0.5 天，预筛约 0.5 天（可选）
- 收益：引用造假/失效可被 lint 机械捕获；chunk 存储为 P2 铺路
- 风险：低（chunker 只写 .meta，不动现有索引；lint 新 check 默认不阻断）

## 6. P2：高级能力（约 2-3 天，按需选做）

### 6.1 chunk 级 BM25 索引

cache.py 的 `build_search_index` 目前整文件一个 doc。扩展为：raw/sources 按 chunk 入库（doc_key = `source:<name>#c001`），query_wiki 新增 `scope="chunks"`。价值：引用校验升级为检索式验证；"哪段原文提到了 X"可直接回答。成本：索引体积 ×N，增量重建逻辑要改。

### 6.2 页面更新合并（对应 WeKnora WikiPageModifyPrompt）

当前同一实体被第二个源文档提及时，Agent 行为未定义（可能重写覆盖）。新增 `page_merge` prompt 类型，规则移植 WeKnora：

- 新信息与已有内容冲突 → 采信新者并加"矛盾/更新"小节；含糊冲突只记录不覆盖
- 仅来源于已 retract 文档的事实应移除（配合 retract_source 流程）
- 保留已有有效内容，合并而非重写

配套在 `_prompt_extract_knowledge` 步骤 5 的 merge 分支引用该模板。

### 6.3 taxonomy 一致性

已有 `taxonomy_plan` prompt（prompt_server.py L1045）但游离在 extract 流程外。做法：

- extract 流程末尾对新建页面跑一次 category 规划（frontmatter category/domain 字段，保持扁平目录不变——不学 WeKnora 建物理子目录，避免 page_router 改动）
- lint 增加 category 值漂移检查（同义词类别告警，如"认证"vs"身份验证"）

### 明确不采纳的 WeKnora 设计

| WeKnora 设计 | 不采纳原因 |
|--------------|-----------|
| pg_trgm 相似度预筛 | CodeWiki 无 PostgreSQL 依赖，BM25/jieba 预筛足够 |
| Go Map-Reduce 并发编排 | CodeWiki 是 Agent-in-loop，编排责任在 Agent，加服务端编排是架构倒退 |
| 物理目录 taxonomy（两级文件夹） | 扁平目录 + frontmatter category 已够用，物理子目录会冲击 page_router 和 wikilink 解析 |
| chunk 别名 c001/c002 | 已有更可读的 `[^src:name:行范围]` 约定且接入 frontmatter 管道 |
| Slug Continuity（更新时复用旧 slug） | CodeWiki 页面即文件，文件名即 slug，天然稳定 |

## 7. effort/benefit 汇总

| 期 | 内容 | 工作量 | 收益 | 依赖 |
|----|------|--------|------|------|
| P0 | 两阶段工作流 + 去重规则 + 编译器纪律 + granularity 透传 | 0.5-1 天 | 消除漏提/误并/幻觉三大主因 | 无 |
| P1 | chunker + cite_refs lint 校验 | 1-1.5 天 | 引用真实性机械保障 | P0（引用约定已存在，实际无硬依赖） |
| P1 可选 | 去重预筛辅助函数 | 0.5 天 | 大批量提取提效 | P0 |
| P2 | chunk 索引 / 页面合并 / taxonomy 一致性 | 2-3 天 | 增量更新与细粒度检索闭环 | P1 |

建议路径：**P0 立即做 → 用真实文档跑一轮冒烟 → 按暴露的问题决定 P1/P2 取舍**。

## 8. 验收标准（冒烟清单）

1. **误并测试**：导入一篇同时提到"居民身份证"和"工作居住证"、"GPT-4"和"GPT-3.5"的文档，确认生成独立页面且互相 wikilink，不合并
2. **幻觉测试**：导入一篇简短文档，要求 focused 粒度，确认不产生仅被提及一次的技术栈实体（如顺带提到的 Redis）
3. **引用测试**：手工在页面中写入行范围越界的 `[^src:...]`，`lint_wiki(checks=["cite_refs"])` 报 error
4. **重复导入测试**：同一文档二次导入，SHA-256 拦截；内容微调后二次导入，已有实体走 merge 分支不产生重复页
5. **回归**：现有冒烟用例全过（OKF 适配冒烟 94/94 基线不退化）

## 9. 涉及文件清单

| 文件 | 改动类型 | 期次 |
|------|---------|------|
| `codewiki/mcp/prompts.py` | 重写 `_prompt_extract_knowledge`，加 granularity 参数 | P0 |
| `codewiki/mcp/tools/doc_writer.py` | 引用正则兼容单行 + sessionless 路径补齐溯源提取（P0 e2e 发现的热修复） | P0 |
| `codewiki/mcp/tools/prompt_server.py` | 新增 extraction_dedup / page_merge；改 extraction_scan / entity_page / concept_page / source_summary | P0+P2 |
| `codewiki/src/chunker.py` | 新增分块器 | P1 |
| `codewiki/mcp/tools/source_ingest.py` | ingest 后触发分块 | P1 |
| `codewiki/mcp/tools/wiki_lint.py` | 新增 cite_refs / category 漂移 check | P1+P2 |
| `codewiki/mcp/tools/wiki_search.py` | （可选）find_similar_pages 预筛 | P1 |
| `codewiki/mcp/cache.py` | （P2）chunk 级索引 | P2 |
