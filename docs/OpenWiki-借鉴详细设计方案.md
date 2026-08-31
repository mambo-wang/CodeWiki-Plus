# OpenWiki 借鉴详细设计方案

> 承接《OpenWiki vs CodeWiki-Plus 对比分析》的借鉴建议清单，给出可落地的详细设计。
> 日期：2026-08-31 · 状态：设计稿（待评审） · 依赖基线：`docs/新鲜度机制设计方案.md`（F1-F3 已落地）、`docs/Phase5-资产治理-实现任务拆解.md`（T1-T8 待排期）。
> 原则：**借分层不借 LLM、借模式不借 hook、借粒度不借无闸门**——人审闸门（draft→confirm、ADR-0002）是立身之本，本方案所有借鉴都只做"证据/信号"，不自动改写文档。

---

## 0. 背景与范围

openwiki（langchain-ai，15.9k stars）是 LangChain 基于 DeepAgents 的"自维护 wiki"CLI，五个值得借鉴的机制：

| 编号 | 借鉴项 | 优先级 | 对标 openwiki 机制 | CodeWiki 现状差距 |
|---|---|---|---|---|
| D1 | 证据锚定的新鲜度判定 | **P0** | Grounded Claims（内容哈希证据 + 行区间重定位 + stale 检测） | 只有时间维度 `stale_after`；`_check_unsupported_claims` 的正文级 `> Evidence:` 无代码绑定、无版本 |
| D2 | 页面级基线 manifest | P1 | `.page-manifest.json` + per-page 基线 diff | `analyze_changes` 行区间近似定位（已知误报） |
| D3 | Mermaid 降级-修复闭环 | P1 | degrade 到 text 围栏 + 注释锚点 + 下次自愈 | 已有 `_auto_fix_mermaid` + `_validate_mermaid` + strict 阻断，缺降级 |
| D4 | no-op 防扰流 | P1 | 多条件 no-op 判定 | watch_repo / doc_update_notify 可能空转 |
| D5 | 文档事实性评测（LEDGER 式） | P2 | Longitudinal 评测 + LLM judge | 完全空白（仅 lint 结构检查） |

**关键既有资产（本方案直接复用，不重复造轮子）：**

- `codewiki/src/frontmatter.py` — 单一 frontmatter 读写层（`inject_okf_frontmatter` / `parse_frontmatter` / `fold_private_metadata` / `format_frontmatter_value`）。私有字段折叠进 `metadata:` 的约定已固化。
- `codewiki/mcp/tools/knowledge_loop.py` — `_apply_status_to_file`（YAML round-trip + verified 追加 + stale_after 续期）、`handle_confirm_note`、`freshness_window_days`。
- `codewiki/mcp/tools/wiki_lint.py` — 20 项检查（`_ALL_CHECKS`），其中 `_check_unsupported_claims`（:923）已实现"正文级断言 + `> Evidence:` 证据行"的雏形。
- `codewiki/mcp/tools/change_analysis.py` — git diff 行级解析 → 组件跨度定位（`locate_changed_components`）→ `transitive_impact` 传递影响。
- `codewiki/mcp/tools/doc_writer.py` — `_build_okf_frontmatter` / `_okf_sources_block` / `_auto_fix_mermaid` / `_validate_mermaid`。
- `codewiki/mcp/cache.py` — `_doc_authority`（0.7-1.3 clamp）、BM25×authority×heat 排序。

---

## 1. D1：证据锚定的新鲜度判定（P0）

### 1.1 现状与差距

CodeWiki 的过期判定**只有时间维度**：`stale_after` 按类型窗口滚动续期（新鲜度机制 F2），lint `stale_notes` 读它报警（F1）。但"文档描述的事实是否随代码漂移"完全没有代码侧证据——某篇模块文档说"XService 负责鉴权"，哪天重构把鉴权挪走了，文档毫无感知，只能等 90/180 天窗口到期被人复核。

现有 `_check_unsupported_claims` 的雏形是**正文内联**的：正文写 `(confidence: X.XX)` 标记断言、`> Evidence: <code quote>` 行给证据。缺点：① 证据是正文里的静态文本，没有版本；② 无法程序化重校验；③ 混在正文里污染可读性。

openwiki 的 Grounded Claims 正是这个雏形的**结构化、版本化**进化：证据锚到 `repo://src/x.ts#L40-L82`，记录证据内容哈希，更新时重解析比对，变了就标 stale。

### 1.2 数据模型：`metadata.evidence`

**全部放进 `metadata` 私有命名空间**（OKF 私有字段约定，零新增顶层字段——与新鲜度专项"零新增字段"纪律一致）：

```yaml
# 模块文档 / 笔记 frontmatter
metadata:
  evidence:
    - id: ev_9f3a21c7              # 稳定 ID（uuid8），供 lint/交叉引用
      resource: "repo://src/server.py#L40-L82"   # 复用 OKF sources 的 resource 语法，新增 repo:// scheme
      version: "sha256:abcd1234..."              # 行区间内容哈希
      file_version: "sha256:ef567890..."         # 整文件哈希（快速失效用）
      scope: "behavior"            # behavior|responsibility|invariant|dataflow|failure|config|security
      established_at: "2026-08-31T08:00:00Z"
```

证据范围 `scope` 直接取 openwiki 的 claim 分类（行为/职责/不变量/数据流/失败语义/配置/安全边界），作为检索时的可信维度。

### 1.3 证据版本化与重定位（借鉴算法，但用更强的"预言机"）

**哈希方案**（对齐 openwiki，便于未来互操作）：

- 整文件：`sha256(file bytes)` → `file_version`
- 行区间：`sha256(指定行内容 joined)` → `version`

**重定位**：openwiki 靠"首/尾行哈希 + 前后 3 行上下文哈希"在代码移动后重定位行区间，歧义即失败。CodeWiki **不需要这套脆弱的启发式**——`DependencyAnalyzer` 的分析图谱本身就维护了 `组件 → 文件 + 行区间` 的映射，组件移动/改名后图谱重分析会给出新位置。因此：

- 失效判定时，若 `resource` 里的行区间哈希变了，**先查分析图谱**：该组件是否仍存在且内容哈希一致？一致 → 组件"搬家"，产出 `relocated` 结果（提示更新 resource，不报 stale）；图谱里也找不到 → 真 stale/删除。

这是"借机制、不借实现"的典型：openwiki 被迫用行上下文哈希，CodeWiki 有组件图谱这个天然更强的重定位预言机。

### 1.4 失效判定：新 lint 检查 `stale_evidence`

新增检查（进 `_ALL_CHECKS`，并同步 `codewiki/mcp/registry.py` 的 checks 枚举——**这是验收期踩过的同步坑，有回归测试 `test_lint_wiki_schema_checks_enum_in_sync` 兜底**）：

对每篇含 `metadata.evidence` 的页面，逐条重解析证据：

| 结果 | 含义 | 严重度 |
|---|---|---|
| `fresh` | 哈希匹配 | — |
| `stale` | 哈希变化（内容被改） | warning |
| `unresolved` | 文件/组件不存在 | warning |
| `relocated` | 组件搬家，建议更新 resource | info |

只报 warning，不自动改写文档（守闸门）。suggestion 文案引导 Agent 走 `edit_doc_file` + `confirm_note(evidence=...)` 复核。

与新鲜度机制的关系：**正交**。`stale_after` 是"多久没人验证"（人侧周期），`stale_evidence` 是"代码证据是否还成立"（代码侧信号）。lint 同时报两类，不互相取代。

### 1.5 与 Phase 5 confidence 的衔接

Phase 5 T1 已规划 `handle_confirm_note` 新增 `evidence` 参数（`{test_ref?, commit_ref?, reviewed_by?}`）→ strong + `metadata.verification`。本方案把 `code_refs` 作为该参数的**第四种证据类型**：

- `confirm_note(evidence={code_refs: ["repo://src/x.py#L10-L30"]})`：确认时计算并写入 `metadata.evidence`（含哈希）+ `confidence_level: strong`。
- 后续 `stale_evidence` 报 stale 时，Agent 复核后可 `confirm_note` 续证或改写——形成"证据 + 置信 + 负反馈"的闭环（Phase 5.2 精神）。

### 1.6 实现任务拆分（D1）

| 子任务 | 内容 | 改动文件 | 依赖 |
|---|---|---|---|
| D1a | 证据哈希工具：`hash_file` / `hash_lines` / `resolve_evidence(resource, repo_path, graph?)` → `{status, version, relocated_resource?}` | 新 `codewiki/src/evidence.py` | — |
| D1b | `write_doc_file` 支持 `evidence_refs` 参数，写入 `metadata.evidence` | `doc_writer.py` | D1a |
| D1c | `handle_confirm_note` 支持 `evidence.code_refs`，确认即落证据 + strong | `knowledge_loop.py` | D1a、Phase5 T1 |
| D1d | lint `stale_evidence` 检查 + 枚举同步 | `wiki_lint.py`、`registry.py` | D1a |
| D1e | `analyze_changes` 输出增加证据交叉：changed components → 命中证据的页面清单 | `change_analysis.py` | D1b、D2 |
| D1f | 测试（`test_evidence.py`：哈希/重定位/失效矩阵/confirm 落证）+ 文档 | `tests/` | 各子项 |

存量页不迁移（无 `metadata.evidence` 即跳过检查），渐进启用。

---

## 2. D2：页面级基线 manifest（P1）

### 2.1 现状

`analyze_changes` 把 diff 行号映射到组件跨度（`start_line..end_line`），删除行锚定到"最近的 new-file 行"——**这是已知的近似**（已有笔记 `analyze-changes-的-changed-components-行区间定位是近似` 记录误报）。且没有"某篇文档上次是根据哪些组件生成的"这种页面级基线。

### 2.2 设计：`.meta/page_manifest.json`

新增 `.meta/page_manifest.json`（与现有 `module_tree.json` / `metadata.json` 并列，原子写临时文件 + `os.replace`）：

```json
{
  "schema_version": 1,
  "pages": {
    "wiki/modules/XService.md": {
      "git_head": "9f3a21c7...",
      "components": ["cid_XService_serve", "cid_XService_auth"],
      "producer": "codewiki/5.6.0",
      "written_at": "2026-08-31T08:00:00Z"
    }
  }
}
```

- **写入**：`handle_write_doc_file` / `handle_edit_doc_file` 成功后 upsert 条目（组件集取该页涉及的 `related_components` / 分析图谱命中的组件）。
- **消费**：`handle_analyze_changes` 结果新增 `pages_touched` 字段——`changed_component_ids ∩ manifest[page].components` 非空的页面即受影响页面。
- **衔接 update_policy**：`update_affected` 策略下，`pages_touched` 就是"需要重新生成的模块文档"的精确清单，取代行区间近似。

**不引入 per-page 内容快照**（openwiki 存了 `sourceFingerprint` + 回滚快照用于失败回滚）：CodeWiki 的正文在 git 里，回滚有 git 本身，无需侧车快照。只存基线指纹即可。

### 2.3 实现任务拆分（D2）

| 子任务 | 内容 | 改动文件 | 依赖 |
|---|---|---|---|
| D2a | manifest 读写 helper（原子写、schema 校验） | 新 `codewiki/mcp/tools/page_manifest.py` 或并入 `doc_writer.py` | — |
| D2b | 写入点接入 write/edit + 组件集采集 | `doc_writer.py` | D2a |
| D2c | `analyze_changes` 输出 `pages_touched` | `change_analysis.py` | D2a |
| D2d | 测试（manifest 生命周期 + 命中交叉） | `tests/test_page_manifest.py` | 各子项 |

工作量约 1 人日。

---

## 3. D3：Mermaid 降级-修复闭环（P1）

### 3.1 现状

`doc_writer.py` 已有三段式：`_auto_fix_mermaid`（写前自动修常见语法错误）→ `_validate_mermaid`（mermaid-parser-py 语法校验，`codewiki/src/be/utils.py`）→ `strict` 模式阻断。缺的是**不可修复图表的优雅降级**：当前非 strict 模式写入带错图，strict 模式直接删文件，两者都没有"降级成可读文本 + 下次自愈"的中间态。

### 3.2 设计

- `_validate_mermaid` 返回结构化结果（失败的 fence 序号 + 脱敏错误信息，而非纯文本串）。
- 非 strict 且存在失败 fence 时，新增 `_degrade_invalid_fences`：把该 ```mermaid fence 改写为 ```text，并在其上方插入注释锚点：

  ```
  <!-- codewiki: mermaid parse failed: <脱敏错误> -->
  ```

  （对标 openwiki 的降级 + 注释锚点策略；错误脱敏复用现有 `sanitize` 思路，压 `--`、截断。）
- `_auto_fix_mermaid` 或 `edit_doc_file` 流程检测到该锚点时优先重绘该图——形成"降级 → 自愈"闭环。
- `strict` 模式行为不变（向后兼容）。

### 3.3 实现任务拆分（D3）

| 子任务 | 内容 | 改动文件 | 依赖 |
|---|---|---|---|
| D3a | `_validate_mermaid` 结构化返回 + 脱敏 | `doc_writer.py`、`codewiki/src/be/utils.py` | — |
| D3b | `_degrade_invalid_fences` + 锚点识别 | `doc_writer.py` | D3a |
| D3c | 测试（降级幂等、strict 不变、锚点修复） | `tests/` | 各子项 |

工作量约 0.5-1 人日。

---

## 4. D4：no-op 防扰流（P1）

### 4.1 现状

`watch_repo` / `doc_update_notify` 触发更新，但没有"这次变更其实不影响文档"的判定，空转会浪费 token 并造成 churn（CodeWiki 已有 `preserve_decisions`、frontmatter additive-only 等防 churn 机制，但触发层仍可能空跑）。

### 4.2 设计

新增判定 helper `is_noop(output_dir, repo_path) -> {noop: bool, reason: str}`，接入 watch_repo 触发链：

1. 上次成功分析的 `git_head`（存 `.meta/project.json` 或 manifest）与当前 HEAD 相同
2. `git status` 工作区干净（排除 `repowiki/` 与被 ignore 路径）
3. `git diff old..HEAD` 只涉及 `repowiki/` 或被忽略路径
4. 指纹双重稳定（project.json 里的 source fingerprint 未变）

全真 → 跳过后续模型工作，只刷新 `last-update` 时间戳（对标 openwiki 的"no-op 不扰动"）。任一假 → 正常进入更新流程。

### 4.3 实现任务拆分（D4）

| 子任务 | 内容 | 改动文件 | 依赖 |
|---|---|---|---|
| D4a | `is_noop` helper + 接入 watch_repo | 新 helper + `codewiki/mcp/tools/watch.py` | — |
| D4b | 测试（四种假条件各自触发更新） | `tests/test_watch.py` 扩展 | D4a |

工作量约 0.5 人日。

---

## 5. D5：文档事实性评测（LEDGER 式，P2）

### 5.1 现状与目标

CodeWiki 有 40+ 测试文件，但全部是单元/集成测试，**没有任何内容级真值评测**——"生成的文档说对了吗"目前无人度量。openwiki 的 LEDGER 提供了范式：回放基准仓库的 git 检查点，用 LLM judge 抽原子事实，对照源码证据打 `supported / stale / invented / unverified` 四率分。

### 5.2 设计（轻量版，不照搬全家桶）

新增 `evals/` 目录（当前不存在）：

- **基准仓库**：新建 2-3 个小样本仓库（或复用 `tests/` 下的 fixtures），各打若干 git 检查点。
- **harness**：`evals/run_doc_grounding.py` 编排——`analyze_repo` → 记录事实基线 → `git checkout` 到下一个检查点 → `analyze_changes`/`review_changes` 增量 → 抽取文档事实 → 判定。
- **LLM judge 外置**（与 distill 三模式同一哲学：CodeWiki 无内置 LLM）：judge 由调用方注入（回调或环境变量配置 model），评测脚本只负责组装上下文、调用 judge、汇总四率分与 `score = supported / current`。
- **产出**：`evals/results/` 下的评测报告 JSON + 摘要。

这是**度量基建**，让 D1/D2 的"证据锚定是否真的降低了 stale 率"可验证，是长期复利项，但成本最高，单独排期。

### 5.3 实现任务拆分（D5）

| 子任务 | 内容 | 改动文件 | 依赖 |
|---|---|---|---|
| D5a | 基准仓库 + git 检查点脚本 | `evals/benchmarks/` | — |
| D5b | harness + judge 注入协议 | `evals/run_doc_grounding.py` | D5a |
| D5c | 四率分指标 + 报告 | `evals/metrics.py` | D5b |

---

## 6. 落地排期与依赖

```
第一批（P0，核心）：
  D1a → D1b ──→ D1e（需 D2b）
  D1a → D1c（需 Phase5 T1 的 evidence 字段，或先自包含实现）
  D1a → D1d
  D1a → D1f
第二批（P1，可并行）：
  D2（D2a→D2b→D2c→D2d）
  D3（D3a→D3b→D3c）
  D4（D4a→D4b）
第三批（P2，独立排期）：
  D5
```

- D1c 与 Phase 5 T1 有字段级耦合：若 T1 先落地，`evidence.code_refs` 直接并入；若想先行，`metadata.evidence` 字段自包含实现，T1 落地时再合并。
- 建议与现有 Phase 5 拆解合并排期：D1 是 T1「evidence 升级」的自然延伸，D2 是「增量更新精度」专项，D3/D4 是质量/效率小项，D5 是「评测锚点」（Roadmap 已提评测锚点需求）。

工作量粗估：D1 约 3-4 人日（核心），D2 约 1 人日，D3 约 0.5-1 人日，D4 约 0.5 人日，D5 约 2-3 人日。合计约 7-9 人日。

---

## 7. 不借鉴项（重申）

| 项 | 理由 |
|---|---|
| personal 模式 + 9 连接器（Notion/Slack/Gmail…） | 偏离"代码库原生"定位，维护成本高 |
| DeepAgents 全家桶 / Ink TUI / PostHog | 技术栈与形态差异，无移植价值 |
| 无闸门自动协调（claims 未提及自动续认） | 人审闸门是 CodeWiki 立身之本；"自动续认"仅在证据校验通过前提下可引入，仍需人确认 |

---

## 8. 风险与兼容

1. **零新增顶层字段**：所有新字段都在 `metadata:` 下（`metadata.evidence`），不触碰 OKF 标准顶层，规避 frontmatter 漂移与 5-writer 同步风险。
2. **lint 枚举同步坑**：`stale_evidence` 进 `_ALL_CHECKS` 必须同步 `registry.py` 的 checks 枚举（回归测试兜底）。
3. **内容哈希伪过期**：格式重排（无语义变化）会触发 stale——用组件图谱重定位 + 行区间哈希（而非整文件）降噪；`file_version` 仅作快速失效粗筛，不单独定罪。
4. **渐进启用**：存量页无 `metadata.evidence`，跳过检查，不迁移、不报错；新页/确认时逐步沉淀。
5. **评测成本**：D5 的 LLM judge 是可选依赖，judge 不可用时评测脚本降级为仅产出事实清单（不判分），不阻塞 CI。
