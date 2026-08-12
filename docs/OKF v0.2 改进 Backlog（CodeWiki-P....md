# OKF v0.2 改进 Backlog（CodeWiki-Plus）

> 生成日期：2026-08-12
> 范围：基于 OKF v0.2 SPEC.md（GoogleCloudPlatform/knowledge-catalog）对 CodeWiki-Plus 的合规性审计，识别出 3 项改进点。

## 目录

1. [P1 · stale\_after 未在所有写入路径注入](#1-p1--stale_after-未在所有写入路径注入违反-v02-5-保鲜期语义)
2. [P2 · 私有 frontmatter 字段未折叠进 metadata: 命名空间，okf\_tags 全局空配置](#2-p2--私有-frontmatter-字段未折叠进-metadata-命名空间okf_tags-全局空配置)
3. [P2 · 根级 .md 缺失 frontmatter](#3-p2--根级-md如-team-memory-hookmd-缺失-frontmatter违反-v02-11-conformance-rule-1)

***

## 1. P1 · stale\_after 未在所有写入路径注入，违反 v0.2 §5 保鲜期语义

### 背景

`schema.yaml` 已配置 `default_stale_days: 90`，且 `codewiki/src/config.py` 定义了 `OKF_VERSION = '0.2'`、`actor_id()`、`OKF_STATUSES` 等单点真相，但**写入 frontmatter 的入口点分散在多个工具里**，导致只有部分路径完整注入了 v0.2 全部可选家族。

### 问题描述

| **写入工具**                                     | **`type`** | **`title`** | **`description`** | **`generated`** | **`stale_after`** | **`sources`**   |
| -------------------------------------------- | ---------- | ----------- | ----------------- | --------------- | ----------------- | --------------- |
| `doc_writer.py`（模块/概念/实体文档）                  | ✅          | ✅           | ✅                 | ✅               | ✅                 | （注入到相关页面）       |
| `wiki_index.py`（根 `index.md`）                | —          | —           | —                 | —               | —                 | —（保留文件，符合 §8）   |
| `capture_conversation.py`（蒸馏原始对话）            | ✅          | ✅           | —                 | ✅               | ❌                 | —               |
| `source_ingest.py`（导入外部源，`raw/sources/*.md`） | ✅          | ✅           | ✅                 | ✅               | ❌                 | ✅（合并到相关 wiki 页） |
| `agents_md.py`                               | ⚠️ 未确认     | ⚠️          | ⚠️                | ⚠️              | ⚠️                | —               |
| `distill_conversation.py`（最终 note）           | ⚠️ 未确认     | ⚠️          | ⚠️                | ⚠️              | ⚠️                | ⚠️              |

> 注：表格中标 ⚠️ 的工具未完整核查源码，需要逐文件确认。

### 具体证据

在 `codewiki/mcp/tools/capture_conversation.py` 的 `handle_capture_conversation` 中写入 frontmatter 时只包含：

```yaml
type: Conversation
title: ...
captured_at: 2026-08-09T...
content_hash: ...
turn_count: ...
link_to: ...
source_session: ...
keep_raw: ...
status: pending
generated: { by: codewiki/5.2.0, at: 2026-08-09T... }
```

**没有 `stale_after` 字段**。同理 `_ensure_source_frontmatter` 给外部源注入时也没补。

### 违反的规范

* **OKF v0.2 §5 (stale\_after)**：规范把 `stale_after` 列为 optional family（可选家族），但强烈推荐——"到期后消费者报告 warning，知识保鲜期"是 OKF 核心语义。`wiki_lint.py::_check_okf_conformance` 已经实现了过期检查（warning），但能否警告取决于有没有写——所以"路径不全"等于"部分知识腐烂了 Lint 还以为没事"。
* **OKF §11 容错消费规则** 反而保护了这种"漏字段"行为，消费者不得拒收，所以问题在表面上静默。

### 建议方案

把所有写入 frontmatter 的入口**收敛到一个 helper 函数**：

```python
# codewiki/src/frontmatter.py  (新文件)
from codewiki.src.config import actor_id
from datetime import datetime, timedelta, timezone

_TZ_CST = timezone(timedelta(hours=8))

def _now_iso() -> str:
    return datetime.now(_TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")

def inject_okf_frontmatter(
    body: str,
    *,
    type_: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    sources: list[dict] | None = None,
    status: str = "draft",
    extra: dict | None = None,
    stale_days: int | None = None,   # None = 不写；0 = 当下过期
) -> str:
    fm: dict = {
        "type": type_,
        "title": title,
        "generated": {"by": actor_id(), "at": _now_iso()},
    }
    if description:
        fm["description"] = description
    if tags:
        fm["tags"] = tags
    if sources:
        fm["sources"] = sources
    if status:
        fm["status"] = status
    if stale_days is not None:
        expired = (datetime.now(_TZ_CST) + timedelta(days=stale_days)).date().isoformat()
        fm["stale_after"] = expired
    if extra:
        fm.update(extra)
    yaml = importlib.import_module("yaml").safe_dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml}---\n\n{body}"


def update_okf_frontmatter(
    text: str,
    *,
    patch: dict | None = None,
    bump_generated: bool = True,
    refresh_stale_after: bool = False,
) -> str:
    """已存在的 .md 不破坏正文，重写 frontmatter。"""
    ...
```

然后让 `capture_conversation.py` / `source_ingest.py` / `agents_md.py` / `distill_conversation.py` / `doc_writer.py` / `write_doc_file` 全部走这个 helper。

`doc_writer.py` 和 `wiki_index.py` 已经在 `feat: 适配 Google OKF v0.2 规范` commit 里改了一版，缺的只是把"模板字符串拼接"换成"helper 调用"。

### 验收标准

- [ ] codewiki/src/frontmatter.py 新建，含 inject_okf_frontmatter() + 单元测试

- [ ] 5 个写入入口（doc_writer / capture_conversation / source_ingest / agents_md / distill_conversation）全部改用 helper

- [ ] default_stale_days: 90 从 schema.yaml 读取并传入 helper

- [ ] 加 lint 规则：检测写入路径里直接用 ---\n 字符串拼 frontmatter 的代码（提示违规）

- [ ] 测试：在 temp_repo 跑 analyze_repo + ingest_source + capture_conversation，三处生成的 frontmatter 必须都含 stale_after 字段

- [ ] okf_conformance 校验的 Wiki 应通过，覆盖率从当前约 60% 升到 100%

### 影响面

* **正面**：知识保鲜语义统一；`wiki_lint` 的 stale\_after 检查从"半有效"变成"全有效"；后续 OKF v0.3 升级只改 helper 即可
* **负面**：5 个工具需要小改造；现有 `repowiki/` 产物需要重新生成一次（stale\_after 字段会更新到新日期）

### 优先级

**P1 — 建议在 5.3.0 合并**。属于"v0.2 形式对齐的最后一公里"，不改的话 OKF 合规度永远停在 90 分。

***

## 2. P2 · 私有 frontmatter 字段未折叠进 metadata: 命名空间，okf\_tags 全局空配置

### 背景

`codewiki/mcp/tools/schema_generator.py` 的 `_DEFAULT_CONVENTIONS` 暴露了 `okf_frontmatter: true` / `okf_version: "0.2"` / `default_stale_days: 90` / `okf_tags: []` 四个开关。前三个都已经生效，但 `okf_tags` 形同虚设——默认值就是空。

同时，多个写入工具在顶层 frontmatter 里**混用了 OKF 字段和项目私有字段**，违反了 OKF 鼓励的命名空间哲学。

### 问题描述

#### 1. `okf_tags` 全局空配置

```yaml
_DEFAULT_CONVENTIONS = {
    ...
    "okf_tags": [],   # ← 形同虚设
}
```

实际效果：所有文档的 `tags` 字段全部为空。即使打开 OKF，`tags` 这个 OKF §4 推荐字段也从未被注入。

#### 2. `CLI.md` 等模块文档的私有字段混在顶层

以 `repowiki/wiki/modules/CLI.md` 为例：

```yaml
---
title: CLI
depth: 1                          # ← 私有
module_type: overview             # ← 私有
component_count: 0                # ← 私有
generated_by: codewiki            # ← 私有
generator_version: "1.0"          # ← 私有
updated_at: 2026-07-28            # ← 私有
type: Module                      # ← OKF
generated: { by: codewiki/5.2.0, at: 2026-08-02T23:41:39Z }  # ← OKF
stale_after: 2026-10-31           # ← OKF
---
```

OKF v0.2 §4 明确**允许任意额外 frontmatter 键**（消费者不得拒收），但视觉噪音明显——OKF consumer 必须二次过滤才能拿到核心字段。

### 违反的规范

* **OKF v0.2 §4 字段命名空间哲学**：规范鼓励"`metadata:` 嵌套或自定义命名空间"，让顶层保持清爽
* **OKF §11 容错消费规则**：因为允许任意键，所以"混用"在规范上不违规，但属于"应做而未做"
* **schema.yaml 自描述一致性**：`okf_tags` 配置项的存在本身就是承诺——留空等于承诺失败

### 建议方案

#### 方案 A（推荐）：私有字段折叠进 `metadata:` 子节点

让 `doc_writer.py` 等工具在生成 frontmatter 时把项目私有字段统一塞进 `metadata:`：

```yaml
---
# OKF 标准字段
type: Module
title: CLI
description: "CodeWiki 的顶层用户入口模块..."
generated: { by: codewiki/5.2.0, at: 2026-08-02T23:41:39Z }
stale_after: 2026-10-31
tags: [codewiki, cli, module]

# 项目私有扩展折叠进命名空间
metadata:
  depth: 1
  module_type: overview
  component_count: 0
  generator_version: "1.0"
---
```

实现要点：

* `codewiki/src/frontmatter.py::inject_okf_frontmatter()` 增加 `metadata_extra: dict | None` 参数
* `doc_writer.py` 等工具把"私有字段"通过这个参数传入
* 顶层只保留 OKF §4 §5 规定的标准字段

#### 方案 B（独立）：启用 `okf_tags` 全局配置

在 `schema_generator.py` 把默认值改为：

```python
_DEFAULT_CONVENTIONS = {
    ...
    "okf_tags": ["codewiki", "auto-generated"],   # 全局默认 tag
}
```

或者让 `inject_okf_frontmatter()` 按 type 自动补 tags：

| **`type`**     | **自动补 tags**                     |
| -------------- | -------------------------------- |
| `Module`       | `["module"]`                     |
| `Concept`      | `["concept"]`                    |
| `Entity`       | `["entity"]`                     |
| `Source`       | `["source"]`                     |
| `Conversation` | `["conversation", "transcript"]` |
| `Runbook`      | `["runbook"]`                    |
| `Comparison`   | `["comparison"]`                 |
| `Query`        | `["decision", "query"]`          |

### 验收标准

- [ ] inject_okf_frontmatter() 增加 metadata_extra 参数

- [ ] 5 个写入工具的私有字段全部进 metadata: 子节点

- [ ] okf_tags 默认值改为 ["codewiki", "auto-generated"] 或实现按 type 自动补

- [ ] 已生成的 repowiki/ 文档通过一次性迁移脚本重写 frontmatter

- [ ] 测试：抽取任意 10 个 .md，顶层只允许出现 OKF §4 §5 规定的字段（含 metadata: 子节点允许私有）

- [ ] 新增 lint 规则：检测"OKF 字段混在顶层 + 私有字段也混在顶层"的违规

### 影响面

* **正面**：OKF consumer 解析 frontmatter 不需要二次过滤；标签全文档统一，跨项目检索可用；顶层一眼区分 OKF 标准字段 vs 项目私有扩展
* **负面**：已生成的 repowiki/ 文档需重写（migration 脚本可批量改）；如果有用户用现有 frontmatter 字段做自动化（如从顶层读 `depth`），需要迁移

### 优先级

**P2 — 建议在 5.3.0 或 5.4.0 合并**。属于"工程质量优化"，不像 `stale_after` 那么紧迫，但能显著提升 OKF consumer 的开发体验。

***

## 3. P2 · 根级 .md（如 team-memory-hook.md）缺失 frontmatter，违反 v0.2 §11 Conformance Rule 1

### 背景

`repowiki/` 目录下有一个根级 Markdown 文件 `team-memory-hook.md`，**不在任何 `wiki/` 等子目录内、又不是 OKF 保留文件名（`index.md` / `log.md`），但也没有 YAML frontmatter**。

按 OKF v0.2 §11 Conformance 三条硬规则严格审视，这个文件违规。

### 问题描述

`repowiki/` 目录结构：

```
repowiki/
├── .meta/                      # OKF 不管（非 .md）
├── notes/                      # 子目录
│   └── *.md
├── raw/sources/                # 暂存（gitignore），里面的 .md 也可能缺 frontmatter
│   └── *.md
├── wiki/                       # Bundle 内容目录
│   ├── index.md                # ✅ 保留文件，有 okf_version frontmatter
│   ├── log.md                  # ✅ 保留文件
│   ├── overview.md             # ✅ 有 frontmatter
│   ├── modules/*.md            # ✅ 全部有
│   ├── concepts/*.md           # ✅ 全部有
│   ├── entities/*.md           # ✅ 全部有
│   └── sources/*.md            # ✅ 全部有
├── ontology.yaml               # 非 .md，OKF 不管
├── schema.yaml                 # 非 .md，OKF 不管
└── team-memory-hook.md         # ⚠️ 根级 .md，无 frontmatter，无 type
```

### 违反的规范

* **OKF v0.2 §11 Conformance Rule 1**：所有非保留 `.md` 含可解析 YAML frontmatter。
* **OKF v0.2 §11 Conformance Rule 2**：每个 frontmatter 含非空 `type`。

`team-memory-hook.md` 同时违反两条。

### 现在的容错行为

OKF §11 还规定："消费者不得因缺可选字段而拒收"——但 frontmatter 缺失/不可解析属于**可拒收**情形。

`wiki_lint.py::_check_okf_conformance` 的实现是：当某文件不以 `---` 开头时报 **error: "Missing YAML frontmatter"**——`team-memory-hook.md` 应该会被这条规则命中（如果 lint 工具扫描了 `repowiki/` 根目录）。

实际情况：lint 工具可能只扫描 `wiki/` 子目录，所以这条违规**漏报了**。

### 建议方案

#### 选项 A（最小改动）：给 `team-memory-hook.md` 加 frontmatter

```markdown
---
type: Runbook
title: "Team-Memory Hook 接线说明"
description: "把 IDE 对话（CodeBuddy SessionEnd/PreCompact/Stop）自动采集到 repowiki/raw/ 的钩子接线文档"
generated: { by: codewiki/5.2.0, at: 2026-08-09T... }
stale_after: 2026-11-07
tags: [codewiki, hook, runbook, team-memory]
metadata:
  audience: IDE integration maintainers
  related: ["codewiki/mcp/_ide_hook.py", ".codebuddy/settings.json"]
---

本文描述如何把 IDE 对话自动采集到 `repowiki/raw/` 暂存区...
```

#### 选项 B（推荐）：移到合适子目录 + 加 frontmatter

`team-memory-hook.md` 不应该放在 Bundle 根——它本质是一个 **Runbook**（运维手册）。建议：

1. 移动到 `repowiki/wiki/runbooks/team-memory-hook.md`
2. 加 frontmatter（如选项 A）
3. `wiki_index.py` 在目录列表里增加 `## Runbooks` 章节
4. `wiki_lint` 扫描根目录兜底也支持（确保未来不会再漏）

#### 选项 C（预防）：加强 lint 扫描范围

在 `wiki_lint.py::_check_okf_conformance` 里：

```python
def _check_okf_conformance(output_dir: Path):
    # 既扫描 wiki/ 子目录，也扫描根目录
    md_files = list(output_dir.rglob("*.md"))
    # 排除暂存/调试目录
    md_files = [
        f for f in md_files
        if "/.meta/" not in str(f)
        and "/.trash/" not in str(f)
        and "/.hook-debug/" not in str(f)
    ]
    # 保留文件豁免 frontmatter 检查
    for md_file in md_files:
        is_reserved = md_file.name in RESERVED_FILES
        ...
```

这样未来任何根级 .md 都会被 lint 抓住。

### 验收标准

- [ ] team-memory-hook.md 加上完整 frontmatter（选项 A 或 B）

- [ ] wiki_lint 扩大扫描范围到 Bundle 根，排除暂存目录

- [ ] 添加测试：故意在 repowiki/ 根加一个无 frontmatter 的 .md，lint 必须报 error

- [ ] repowiki/team-memory-hook.md（如有）在 frontmatter 里显式声明 tags / metadata.audience

### 影响面

* **正面**：严格符合 OKF v0.2 §11（不再有静默违规）；lint 不会漏报根级 .md；移动到子目录后语义清晰（Runbook 是 wiki 的一部分而非 Bundle 根元数据）
* **负面**：`repowiki/` 目录结构变更需在 README 里同步；如果有自动化脚本读 `repowiki/team-memory-hook.md` 路径，需要更新

### 优先级

**P2 — 建议在 5.3.0 合并**。属于"v0.2 严格合规的最后一公里"，体量很小但意义在于让 lint 不留死角。

***

_以上 3 项改进点整理自 OKF v0.2 规范审计（2026-08-11），可作为 CodeWiki-Plus 后续版本 backlog 追踪。_
