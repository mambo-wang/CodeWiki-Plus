# OKF v0.2 适配方案

> 版本目标：CodeWiki-CN 5.1.8 → **5.2.0**（minor bump，语义为"新增向后兼容能力"）
> 规范依据：[GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog) `okf/SPEC.md` v0.2（2026-07-28 发布）
> 本地参考副本：`D:\repos\knowledge-catalog\okf\SPEC.md`（1003 行，含 §13 变更说明与附录 A 完整示例）

## 0. 结论与原则

CodeWiki 与 OKF 高度同构（bundle = repowiki/、type 必填、index/log 保留文件均已存在），
且 v0.2 相对 v0.1 的两个破坏性变更（`timestamp`→`generated.at`、`# Citations`→`sources`）
我们从未使用（现有是自创的 `generated_from` 与 `source_refs`），**无历史包袱，可直接对齐 v0.2 词汇表**。

三条原则：

1. **只增不删**：现有自创字段（`aliases`、`related_modules`、`source_refs`、`generated_from`、
   `severity`、`root_cause` 等）全部保留——OKF 明确允许 producer 扩展键，消费端 MUST NOT 拒绝。
2. **不新增 MCP 端点**：行为变更走 prompt（get_prompt 的 OKF 段）与现有工具参数，
   迁移用一次性脚本完成，不给 MCP 表面增加负担。
3. **读端双兼容**：所有读取方（query_wiki、lint、html 导出）同时接受新旧词汇，
   写端输出新词汇，存量由迁移脚本一次转换。

明确不做：`Attested Computation`（代码文档场景无"受制裁计算"；规范允许未知 type，消费端必须容忍）；
receipt/attester 运行时协议（v0.2 规范自身已 defer 到下个版本）。

---

## 1. 现状盘点（差距来源）

已具备：

- `_build_okf_frontmatter()`（doc_writer.py:228）生成 `type/title/description/resource/tags`
- schema.yaml conventions 有 `okf_frontmatter: true` / `okf_tags`
- get_prompt 输出 OKF 基础规范（prompt_server.py:104）
- 笔记生命周期 candidate→confirmed/rejected（knowledge_loop.py），语义上对应 OKF trust tier
- staleness 机制（retrieval_stats.db + lint 90/60 天阈值）
- 外部文档登记（source_registry.json + ingest/retract_source）

差距（按 SPEC 章节）：

| # | 规范要求 | 现状 | 阶段 |
|---|---|---|---|
| G1 | §11 合规：所有非保留 .md 有可解析 frontmatter 且 `type` 非空 | 本仓库 29 个 md 中 26 个缺 type、3 个无 frontmatter；根因：内容自带 frontmatter 时注入被整体跳过（doc_writer.py:251 `content.startswith("---")` 直接 return None） | P0 |
| G2 | §5.2 `generated: {by, at}` + §7 actor 约定 | 只有 `generated_from: <git sha>` | P1 |
| G3 | §5.2/§5.3 `verified` 列表 + 信任层派生 | confirm/reject 只改 status 字段，不记录验证事件 | P1 |
| G4 | §5.4 `status: draft/stable/deprecated` | 用 candidate/confirmed/rejected/superseded | P1 |
| G5 | §5.5 `stale_after: YYYY-MM-DD` | 无（staleness 只在 lint 运行时推算） | P1 |
| G6 | §5.1 `sources` 字段族 + 按 id 的脚注归因 | 自创 `source_refs` + `[^src:name:range]` 脚注 | P2 |
| G7 | §12 根 index.md `okf_version: "0.2"` | 无 | P3 |
| G8 | §8 index.md 格式（`* [Title](url) - desc` 分组 bullet） | 表格 + Health Score 行（wiki_index.py `_render_index`） | P3 |
| G9 | §9 log.md 格式（`## YYYY-MM-DD` 倒序分组 bullet） | 追加式表格、正序（wiki_index.py `append_log`） | P3 |
| G10 | §11 合规范围覆盖 raw/sources/*.md | ingest_source 拷贝原文不加 frontmatter | P3 |

---

## 2. P0 — frontmatter 覆盖修复（合规前置）

**改 `skip` 为 `patch`。** 核心变更在 doc_writer.py：

1. 新增 `_merge_okf_frontmatter(existing_fm: str, defaults: dict) -> str`：
   - `yaml.safe_load` 解析已有 frontmatter；解析失败 → 原样保留并在返回值中标记 warning
   - 逐键补齐缺失的 OKF 字段：`type`（按 page_type 映射，见现有 `_TYPE_MAP`）、
     `title`、`description`；已存在的键一律不覆盖
   - 保留全部用户自定义键（OKF 扩展键合法）
2. `_build_okf_frontmatter()` 的提前返回（doc_writer.py:251-252）改为：
   content 以 `---` 开头 → 走 `_merge_okf_frontmatter` 而非 return None
3. `_inject_lightweight_frontmatter`（sessionless 路径）同步改造
4. overview.md 生成路径（close_session 的 rebuild）确认注入 `type: Architecture`

**迁移脚本 `scripts/migrate_okf.py`**（一次性、非 MCP 端点）：

- 扫描 `repowiki/wiki/**/*.md` + `notes/*.md`
- 无 frontmatter → 补最小 frontmatter（type 按目录推断：modules/→Module、queries/→Query …）
- 有 frontmatter 缺 type → patch
- status 旧值映射（见 P1-3）
- 幂等：重复运行不重复写入
- 干跑模式 `--dry-run` 先输出变更清单

**验证**：对当前仓库运行迁移后，用 §11 三条合规标准复扫，要求 29/29 通过。

---

## 3. P1 — trust 与 lifecycle（generated / verified / status / stale_after）

### 3.1 actor 约定（§7）

`codewiki/src/config.py` 新增：

```python
ACTOR_NAME = "codewiki"


def actor_id() -> str:
    from codewiki import __version__

    return f"{ACTOR_NAME}/{__version__}"  # e.g. codewiki/5.2.0
```

所有 `generated.by` / 默认 `verified.by` 统一走 `actor_id()`，避免版本号散落。

### 3.2 generated（doc_writer.py）

`fm_parts` 中在保留 `generated_from`（sha，扩展键）的同时追加：

```yaml
generated: { by: codewiki/5.2.0, at: 2026-08-03T12:00:00Z }
```

`at` 取写入时刻 UTC ISO8601（现有 `_gen_from` 的 datetime 分支可复用）。

### 3.3 verified 与信任层（knowledge_loop.py）

- `handle_confirm_note`：`_update_note_status(..., "confirmed")` 之后，向 frontmatter
  追加/更新 `verified` 列表：

  ```yaml
  verified:
    - { by: human:wangbao, at: 2026-08-03T12:30:00Z }
  ```

  confirm_note 增加可选参数 `by`（缺省 `codewiki/<ver>`；用户显式确认场景传 `human:<id>`）。
  重复 confirm 追加新条目（规范支持多次独立验证），`stale_after` 同步续期（见 3.5）。
- `handle_reject_note`：status→deprecated 语义（见 3.4），不加 verified。
- query_wiki 输出侧按 §5.3 派生信任层展示：无 verified → unverified；
  仅非 human → machine-confirmed；含 `human:` → human-reviewed。
  `[unconfirmed]` 前缀逻辑改为：status==draft 或无 verified 时显示。

### 3.4 status 词汇迁移（§5.4）

写端输出 OKF 词汇，读端双兼容：

| 旧值 | 新值 |
|---|---|
| candidate | draft |
| confirmed | stable |
| rejected | deprecated |
| superseded | deprecated（body 内保留 superseded-by 链接） |

- 读端改造点：query_wiki 的 status 过滤（knowledge_loop.py:947 附近）、
  lint 的 `_check_stale_notes`（status=="confirmed" 判断）、`_check_superseded_pages`
- 新值判断统一写成 `_norm_status(s)` 辅助函数：`{"candidate":"draft","confirmed":"stable",...}.get(s, s)`
- ingest_note 的 `status` 参数：接受新旧两套值，写盘前归一为新词汇；
  工具描述（registry.py）同步更新 enum
- 存量文件由 migrate_okf.py 转换

注意：`deprecated` 文件保留不删（§5.4 规范语义：kept for links and history），
与现有 reject 行为（保留文件+reason）一致。

### 3.5 stale_after（§5.5）

- schema.yaml conventions 新增 `default_stale_days: 90`（schema_generator.py 默认值同步）
- 写入时机：ingest_note / write_doc_file 注入 frontmatter 时追加
  `stale_after: <today + default_stale_days>`（YYYY-MM-DD）
- confirm_note 续期：重新确认 = 重新担保时效，`stale_after` 重置为 now+90d。
  这与现有 `_check_stale_notes`（90 天 + 无近期检索）语义闭环
- lint 新增读取：`today >= stale_after` → 并入 stale_notes/stale_refs 报告
  （P4 的 okf_conformance 检查兜底）

---

## 4. P2 — provenance（sources 字段族，§5.1）

### 4.1 双写 sources

source_registry.json 条目已含 path/original_path/description/imported_at/content_hash，
映射关系：

```yaml
sources:
  - id: mcp_smoke_src_a                    # registry name
    resource: raw/sources/mcp_smoke_src_a.md   # bundle 相对路径
    title: <description>
    last_modified: <imported_at 的日期部分>
```

- ingest_source 时：除现有 `source_ref` 注入外，向 related_pages 的 frontmatter
  写入/合并 `sources` 列表（幂等，按 id 去重）
- retract_source(mode=remove_refs) 时：同步移除对应 sources 条目
- 保留 `source_refs`/`chunk_refs`（扩展键，内部工具继续用）

### 4.2 脚注归因格式

- 新格式：`[^<source-id>]`，label = registry name（§5.1 按 id 键控）
- `_extract_source_refs` 兼容双格式：旧 `[^src:name:start-end]` 与新 `[^name]` 都能抽取
- get_prompt 的写作指引改为示范新格式；旧文档不强制改写（lint 只报 info 级提示）

### 4.3 usage_count / usage_window（可选，P2b）

retrieval_stats.db 已按文档记录检索次数，可映射为 source 级 `usage_count` +
`usage_window: {from: today-30d, to: today}`。收益一般，建议先不做，
等 OKF 生态消费端真的读这个字段再补。

---

## 5. P3 — bundle 结构（index / log / okf_version / raw 边界）

### 5.1 okf_version

rebuild_index 写根 index.md 时带 frontmatter（§12：这是 index.md 唯一允许的 frontmatter）：

```yaml
---
okf_version: "0.2"
---
```

schema_generator 默认 conventions 增加 `okf_version: "0.2"`。

### 5.2 index.md 格式（wiki_index.py `_render_index`）

改为 §8 bullet 结构，Health Score 移入 HTML 注释（不破坏合规、信息不丢）：

```markdown
---
okf_version: "0.2"
---

<!-- 自动生成于 2026-08-03T12:00:00+08:00 | Health Score: 100/100 -->

# 模块文档

* [AnalysisPipeline](modules/AnalysisPipeline.md) - 分析流水线，负责…
* [CLI](modules/CLI.md) - 命令行入口…

# 知识笔记

* [xxx 经验](../notes/2026-08-01-xxx.md) - draft | 2026-08-01
```

注意：`_extract_doc_title_and_summary` 目前从正文 H1 取标题，应优先读 frontmatter
的 `title`/`description`（§8：entries SHOULD include the description from frontmatter）。

### 5.3 log.md 格式（wiki_index.py `append_log`）

改为 §9 倒序日期分组。实现：读现有文件 → 定位/创建 `## <today>` 小节
（紧跟标题块之后插入，保持倒序）→ 追加 `* **<op>**: <summary>`。
现有 `_log_create_lock` / `_append_with_lock` 锁机制保留，但写入方式从纯 append
改为"读-改-写"，需在 `_index_lock` 同级加锁保护整体操作。

存量表格日志不转换（历史记录，git 可查）；迁移脚本在旧表格前加一行
`<!-- 以下为 v5.1.x 旧格式日志存档 -->` 分隔即可。

### 5.4 raw/sources 边界（G10）

bundle 边界声明为 `repowiki/` 全树，raw/sources/*.md 也须合规：
ingest_source 拷贝后为 .md 文件注入最小 frontmatter
（`type: Source` + `title` + `status: stable` + `generated`）。
非 md 文件（pdf 等）不受 §11 约束，不动。

---

## 6. P4 — lint 与 prompt

### 6.1 新增 `okf_conformance` 检查（wiki_lint.py，第 16 项）

CHECKS 元组追加 `"okf_conformance"`，检查项：

1. wiki/ + notes/ 所有 .md frontmatter 可解析且 `type` 非空（G1）
2. `verified` 若存在：bare mapping 或 list 均合法；`by`/`at` 齐全
3. `status` ∈ {draft, stable, deprecated}（旧值 → warning 提示跑迁移脚本）
4. `stale_after` 已到期 → warning（复用 stale_notes 的报告格式）
5. 根 index.md 有 `okf_version`；index/log 保留文件结构抽查

registry.py 的 lint_wiki 工具描述 enum 15→16。

### 6.2 prompt 更新（prompt_server.py:104 附近）

OKF 段落扩写为 v0.2 版：新增 `generated`/`verified`/`status`/`stale_after`/`sources`
字段说明、actor 约定（`codewiki/<ver>` / `human:<id>`）、按 id 脚注归因示例。
get_prompt enum 不变（不新增模板）。

---

## 7. P5 — 测试与发布

### 7.1 测试

- smoke_test 新增用例：
  - frontmatter patch：自带无 type frontmatter 的内容写入后 type 被补齐、自定义键保留
  - confirm_note 追加 verified 条目 + stale_after 续期
  - status 读端兼容：旧值 candidate 文件仍可被 query_wiki 按 draft 过滤命中
  - rebuild_index 输出含 okf_version 且为 bullet 结构
  - append_log 同日多次写入归入同一日期小节、倒序
  - lint okf_conformance 对构造的坏样本正确报告
- 新增 tests/test_okf_migration.py：migrate_okf.py 幂等性 + 旧值映射

### 7.2 版本号（4 处同步，bump 5.1.8 → 5.2.0）

| 文件 | 位置 |
|---|---|
| pyproject.toml | line 7 |
| codewiki/__init__.py | line 8 |
| codewiki/mcp/server.py | line 129 |
| codewiki/src/be/documentation_generator.py | line 50 |

### 7.3 文档

- README / CodeWiki介绍.md：新增 "OKF v0.2 conformant" 段落
- AGENTS.md（项目级）：使用建议中提一句 lint_wiki 新增 okf_conformance
- 发布后按 AGENTS.md 约定，把"适配 OKF v0.2"作为 decision 笔记 ingest 归档

---

## 8. 风险与验证项

| 风险 | 缓解 |
|---|---|
| ~~index/log 格式变更影响下游解析~~ | **已排除**：全库 grep 确认无代码解析 log/index 表格结构——page_router.py 仅做文件路由、wiki_search.py 将二者列入 `_SYSTEM_FILES` 排除、html_generator 无引用。格式可放心改 |
| status 词汇变更破坏存量笔记过滤 | 读端 `_norm_status` 双兼容 + 迁移脚本兜底 |
| log.md 改"读-改-写"引入并发问题 | 全程持锁 + 原子写（tmp+rename，复用 `_atomic_write`） |
| frontmatter patch 误伤用户手写内容 | 只补缺失键、不覆盖、不排序；解析失败时原样保留并 warning |
| PyPI 版本冲突 | bump 5.2.0 唯一性发布前 `pip index` 确认 |

## 9. 工作量估计

| 阶段 | 内容 | 估计 |
|---|---|---|
| P0 | frontmatter patch + 迁移脚本 | 0.5 天 |
| P1 | generated/verified/status/stale_after | 0.5 天 |
| P2 | sources 双写 + 脚注格式 | 0.5 天 |
| P3 | index/log/okf_version/raw 边界 | 0.5 天 |
| P4 | lint + prompt | 0.5 天 |
| P5 | 测试 + 版本 + 文档 | 0.5 天 |
| 合计 | | ~3 天 |
