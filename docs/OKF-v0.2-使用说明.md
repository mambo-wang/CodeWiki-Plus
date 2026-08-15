# CodeWiki-Plus 对 OKF v0.2 规范的使用

本文档描述 CodeWiki-Plus **当前实际实现**的 OKF（Open Knowledge Format）v0.2 用法，面向需要理解、校验或扩展 frontmatter 的开发者与 Agent。

- 设计背景与改造方案见 [`OKF-v0.2-适配方案.md`](./OKF-v0.2-适配方案.md)
- 已知待办见 [`OKF v0.2 改进 Backlog`](./OKF%20v0.2%20改进%20Backlog（CodeWiki-P....md)

---

## 1. 总览

OKF v0.2 通过 YAML frontmatter 让每篇知识文档携带**机器可读的溯源与生命周期元数据**。CodeWiki-Plus 的核心理念是：

> **顶层只放 OKF 标准字段；生产者私有字段折叠进 `metadata:` 节点。**

所有写入路径（`write_doc_file` / `ingest_note` / `capture_conversation` / `source_ingest`）共享同一套 frontmatter 生成逻辑，单一事实来源在 `codewiki/src/frontmatter.py`。

### 顶层标准字段（§4/§5/§7）

| 字段 | 含义 | 必填 |
|------|------|------|
| `type` | 文档类型（首字母大写） | ✅（lint 报 error） |
| `title` | 标题 | 建议 |
| `aliases` | 别名/搜索 slug | 可选 |
| `description` | 摘要（正文首段截取 ≤200 字） | 可选 |
| `tags` | 标签列表 | 可选 |
| `status` | 生命周期状态 | 可选 |
| `verified` | 验证记录 | 可选 |
| `stale_after` | 保鲜截止日期 | 可选 |
| `generated` | 溯源 `{ by, at }` | 建议 |
| `sources` | 源文档引用（§5.1） | 可选 |
| `metadata` | 生产者私有字段折叠节点 | 可选 |

定义见 `frontmatter.py` 的 `_OKF_STANDARD_KEYS`，lint 侧对应 `wiki_lint.py` 的 `_OKF_TOP_LEVEL_KEYS`（多含一个 `metadata`）。

---

## 2. frontmatter 示例

```yaml
---
type: Module
title: "订单引擎核心"
description: "负责订单的创建、状态流转与回调通知"
tags: ["my-repo", "order_engine"]
generated: { by: codewiki/5.2.2, at: 2026-08-15T08:00:00Z }
stale_after: 2026-11-13
aliases: ["order_engine"]
status: stable
metadata:
  resource: "file://src/order/engine.py (+3 more)"
  generated_from: "a1b2c3d"
  source_refs: ["src/order/engine.py"]
  chunk_refs: []
sources:
  - id: order-engine-sdk
    resource: "https://example.com/order-sdk"
    title: "Order SDK 官方文档"
    last_modified: "2026-01-01"
---
```

---

## 3. 字段详解

### 3.1 `type`（§4，必填）

由 `page_type` 映射而来（`doc_writer.py`）：

| page_type | type 值 |
|-----------|---------|
| `module` | `Module` |
| `entity` | `Entity` |
| `concept` | `Concept` |
| `source` | `Source` |
| `comparison` | `Comparison` |
| `query` | `Query` |

特例：`capture_conversation` 写 `type: Conversation`；`source_ingest` 写 `type: Source`。

### 3.2 `generated` 与 actor 约定（§7）

`generated.by` 遵循 actor 规范：

| 形态 | 格式 | 示例 |
|------|------|------|
| agent / tool | `<producer>/<version>` | `codewiki/5.2.2` |
| 人类 | `human:<id>` | `human:wangbao` |
| 流水线 | `process:<id>` | `process:ci-nightly` |

事实来源：`codewiki/src/config.py` 的 `actor_id()` 返回 `f"{ACTOR_NAME}/{__version__}"`（即 `codewiki/5.2.2`，**不含 `agent:` 前缀**）。

`generated.at` 为 UTC ISO 8601 时间戳（`%Y-%m-%dT%H:%M:%SZ`）。

### 3.3 `status`（§5 状态词表）

标准词表：`draft` / `stable` / `deprecated`。

旧词表自动归一化（`_norm_status` / `_STATUS_LEGACY_MAP`）：

| 旧状态 | OKF v0.2 |
|--------|----------|
| `candidate` | `draft` |
| `confirmed` | `stable` |
| `rejected` | `deprecated` |
| `superseded` | `deprecated` |

### 3.4 `verified` 与信任层（§5.3）

`verified` 为单个 mapping 或 list of mapping（`{ by, at, note? }`）。信任层由 `_trust_tier()` 从 `verified[].by` 推导：

| 信任层 | 判定条件 |
|--------|----------|
| `unverified` | 无 `verified` 字段 |
| `machine-confirmed` | 有 `verified` 但 `by` 不以 `human:` 开头 |
| `human-reviewed` | 任一 `verified.by` 以 `human:` 开头 |

### 3.5 `stale_after`（§5.5 保鲜期）

绝对日期 `YYYY-MM-DD` = 生成日 + `default_stale_days`（`schema.yaml` 默认 90 天）。

重新确认（`confirm_note` → `stable`）会**续期** `stale_after`，重置为 now + `default_stale_days`。

### 3.6 `sources`（§5.1 溯源）

从 `source_registry.json` 生成，每项含 `id` / `resource` / `title` / `last_modified`，仅收录 `status != "retracted"` 的源。实现见 `doc_writer.py` 的 `_okf_sources_block`。

### 3.7 `metadata:`（生产者私有字段折叠）

非 OKF 标准的字段一律折叠进 `metadata:` 节点。历史顶层私有字段（`PRIVATE_FRONTMATTER_KEYS`）包括：

`resource`、`generated_from`、`category`、`domain`、`version`、`format`、`decision`、`decided_at`、`severity`、`root_cause`、`captured_at`、`content_hash`、`turn_count`、`link_to`、`source_session`、`keep_raw`、`task_id`、`date`、`summary`、`keywords`、`origin`、`related_modules`、`related_components`、`source_ref`、`source_refs`、`chunk_refs`

**例外**：`capture_conversation` 通过 `top_level_extra` 将 `link_to`/`keep_raw`/`content_hash` 等**保留在顶层**，因为蒸馏流程（`distill_conversation`）用简单行解析（`^key: value`）读取这些字段，折叠会破坏蒸馏。

---

## 4. 各写入路径的行为

| 写入路径 | 工具 | 默认 status | 说明 |
|----------|------|-------------|------|
| Wiki 页 | `write_doc_file` / `generate_docs` | `stable` | `_build_okf_frontmatter` 生成 |
| 知识笔记 | `ingest_note` | `draft` | `_update_note_status` 确认后升 `stable` |
| 对话暂存 | `capture_conversation` | `pending` | `stale_days=90`，`top_level_extra` 保留蒸馏字段 |
| 源文档 | `source_ingest` | `stable` | `type: Source` |

`confirm_note` / `reject_note` 通过 `_apply_status_to_file` 改写 `status`，并可选追加 `verified` 条目、续期 `stale_after`。

---

## 5. 校验（`wiki_lint` 的 `okf_conformance` 检查）

`wiki_lint.py` 的 `_check_okf_conformance` 逐条校验：

1. **`type` 缺失** → `error`（§4 唯一必填）
2. **未知顶层字段** → `warning`（非标准且非 legacy 字段应折叠进 `metadata:`）
3. **legacy 状态词** → `warning`（提示迁移到 OKF 词表）
4. **未知状态** → `warning`
5. **`verified` 结构非法** → `warning`
6. **`stale_after` 已过期** → `warning`
7. **`wiki/index.md` 未声明 `okf_version`** → `warning`（§12）

**扫描豁免**：`raw/` 根目录下的暂存文件（`conv-*.md`）跳过，但 `raw/sources/` 仍参与审计（真实源文档层）；`.meta/`、`.trash/`、`.hook-debug/` 也跳过。

---

## 6. 迁移（`scripts/migrate_okf.py`）

用于修复历史文档：

```bash
python scripts/migrate_okf.py --fold-private repowiki
```

功能：
- 回填缺失的 `type` 字段
- 迁移 legacy 状态词到 OKF 词表
- `--fold-private`：将顶层私有字段折叠进 `metadata:`
- 修复 Windows 路径拆入导致的 YAML 无效转义（`\c` → `\\c`）
- 为 `wiki/index.md` 补写 `okf_version: "0.2"`

---

## 7. 配置（`schema.yaml`）

| 键 | 默认值 | 作用 |
|----|--------|------|
| `conventions.okf_frontmatter` | `true` | 强制 OKF frontmatter |
| `conventions.okf_version` | `"0.2"` | 写入 `index.md` 的 `okf_version` |
| `conventions.default_stale_days` | `90` | 计算 `stale_after` |
| `conventions.okf_tags` | `[]` | 全局追加标签 |

---

## 8. 与检索的关系

OKF frontmatter 字段**不进入** `query_wiki` 的 BM25 全文索引，因此新增/调整 frontmatter 字段不影响检索结果。检索仍基于正文内容；`aliases`/`tags` 用于搜索索引与链接解析，`status`/`stale_after` 用于过滤过期与未确认知识。
