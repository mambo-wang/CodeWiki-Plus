---
type: Conversation
title: "conversation 20260902T052319Z"
status: distilled
stale_after: 2026-12-01
generated: { by: codewiki/5.5.1, at: 2026-09-02T05:23:19Z }
captured_at: "2026-09-02T05:23:19Z"
content_hash: "sha256:2117c083ffcda9f1b30f70b1d01458fd79058edbde725bbaedb37bbef824fb42"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: ""
source_session: "a70c4262ff7b49b7bb180a3737a6b6f1"
turn_count: 30
---

# Conversation Transcript

user: 本周改动有点大，请把CODEWIKI MCP整体测试一遍，重点测试最近一周的改动
user: <question>本会话是否需要关联到某个进行中的任务？（关联后会话中的对话会自动归档到该任务的记忆）</question>
<answers>
跳过(本次会话不做任务关联，直接开始干活)
</answers>
</question_item>
</questions>
</question_answer>
assistant: 好的，跳过任务关联，直接开始测试。先摸清最近一周的改动范围和 MCP 的整体结构。
assistant: git log 被截断了，让我看完整的改动范围，重点筛选出 `codewiki/mcp` 的代码改动。
assistant: 改动范围已清楚。最近一周的核心代码改动集中在几块：**多仓工作区（集中式布局，工单 01-10）**、**KnowledgeStore 统一存储层重构**、**P0 证据锚定（stamp_evidence）**、**D2 页面级 manifest（page_manifest/stale_pages）**、以及若干修复。先看测试配置和 MCP 冒烟测试，再确定测试策略。
assistant: 现在了解 MCP 工具注册表和最近改动核心文件。先看 registry 和最近改动的关键文件。
assistant: 改动量很大（+2571/-1247 行），核心是 3 个新文件（`page_manifest.py`、`evidence.py`、`store_bridge.py`）加 4 个大改文件（`workspace_bootstrap.py`、`workspace_analyzer.py`、`wiki_lint.py`、`registry.py`）。现在先跑全量测试基线，同时看 registry 确认工具全貌。
assistant: 全量 pytest 基线：**643 passed, 2 skipped**，全绿（5 分钟）。接下来跑 MCP 冒烟测试（直接调真实 handler），并核对 registry 工具清单，确认哪些改动路径有测试覆盖、哪些没有。
assistant: 冒烟测试 131 过 1 挂：`prepare carries transcripts` 失败。这个失败很关键——可能揭示 Mode C 的 prepare 输出结构变化。先查 `distill_conversation.py` 的 prepare 实现和最近改动，同时看 registry 工具清单。
assistant: 关键发现：`distill_conversation.py` 的 Mode C prepare 已改为 **file-side-channel**（只回 `full_path` + 元数据 + 短 preview，不内联完整 transcript）。而 smoke test 还在断言 `transcript` 字段含正文——这可能是**过时的测试断言**而非功能 bug。需要核实 prepare 实际返回结构。
assistant: 确认了两件事：
1. **registry 共 48 个工具**，`stamp_evidence` 已注册（新）。
2. **冒烟失败是过时断言**：`distill_conversation` 的 Mode C prepare 已按 file-side-channel 改为返回 `preview` 字段（不再内联完整 `transcript`），但 `smoke_test_mcp.py` 还在断言旧的 `transcript` 字段。产品功能正常，测试断言需同步。

先修复该断言：
assistant: 重新跑冒烟测试确认修复，同时看 server.py 了解协议层启动方式。
assistant: 冒烟测试修复后全绿（132/132）。现在做**协议层端到端测试**——用真实的 MCP stdio client 连 server，验证工具能正常收发。先读 registry 中新工具的 schema，确保调用参数正确。
assistant: 掌握了新工具 schema。写一个**协议层端到端检查脚本**（真实 MCP stdio client 连 server），覆盖最近一周的关键改动路径。先确认 `lint_wiki` 的检查名和 `doc_writer` 的 manifest 写入点，避免断言写错。
assistant: 确认了关键接入点：`lint_wiki` 有 `stale_evidence` 检查、`doc_writer` 三处写入 `page_manifest`、`batch_ingest` 支持 `items_file` 文件侧通道。现在写协议层端到端脚本，覆盖最近一周全部关键改动路径。
assistant: E2E 出了 8 个失败，需要逐个甄别是脚本断言问题还是真实 bug。其中 `init_workspace` 生成物缺失、`stale_evidence` 新鲜盖章即报 stale、`query_wiki` 未命中——这 3 个最可疑，可能是真实 bug。先看 `init_workspace` 实现和 `_check_stale_evidence` 实现。
assistant: 发现一个关键问题线索：`_check_stale_evidence` 用 `repo_root = output_dir.parent` 猜 repo 根，而 `stamp_evidence` 时用户传入的 `repo_path` 没有被记录复用。在 centralized 布局（最近新增）下 output_dir.parent 不是任一成员仓根，会误报。先验证 `evidence.py` 的 stamp/verify 是否记录 repo 信息，同时读 `handle_init_workspace` 实现确认生成物路径。
assistant: 抓到一个测试脚本自身的 bug：MCP server 是独立子进程，它的 cwd 是**脚本启动时**的目录（`d:/repos/CodeWiki-CN`），我脚本里 `os.chdir(ws)` 不影响子进程。所以 `init_workspace` 可能写到了工作区根——先检查工作区是否被污染。
assistant: 确认污染：`init_workspace` 写到了工作区根（生成了 `bootstrap.sh/ps1`、`workspace.json`、`repo-map.md`，还改了 `AGENTS.md`）。这是测试脚本 cwd 传递的 bug 造成的，需立即清理并恢复。`uv.lock` 的改动也顺便看一下。
assistant: 污染已清理，工作区只剩我的测试脚本和 smoke 断言修复。现在查 `query_wiki` 返回结构（确认 title 字段是否存在），然后修正 e2e 脚本。
assistant: `query_wiki` 对 draft note 的 title 会加 `[unconfirmed]` 前缀，且结果里有 `title` 字段——之前失败可能是断言逻辑问题。现在修正 e2e 脚本（显式传 `workspace_path`、修正断言字段、补充 centralized/colocated 双场景验证 `stale_evidence`）。
assistant: E2E 整体 **30 过 1 挂 1 观察**。两个结论：
1. `layout persisted` 失败是脚本断言字段名错了（实际是 `wiki_layout`），产品正常。
2. **确认真实问题**：centralized 布局下 `stale_evidence` 误报 `evidence file disappeared`（colocated 正常）。根因是 `_check_stale_evidence` 用 `output_dir.parent` 猜 repo 根，而 centralized 布局下 output_dir.parent 不是成员仓根。这是「多仓 centralized 布局」与「P0 证据锚定」两个新功能的集成漏洞。

先修正断言，并确认该场景是否有测试覆盖、看 workspace.json 里有没有可用的成员仓映射信息（评估修复方向）。
assistant: 确认了测试缺口：`test_evidence.py` 完全没有 centralized/repo 映射覆盖，而 `repo_root = output_dir.parent` 是硬编码推断。看 `workspace.json` 在 centralized 布局下是否记录了成员仓映射（评估修复可行性），并核对 `verify_entry` 签名与 server 版本号。
assistant: 修正理解：centralized 布局下**每个成员仓的 repowiki 仍在仓根内**（`<workspace>/<name>/repowiki`），所以成员仓 lint 时 `output_dir.parent` 依然正确。我之前的 4b 模拟了非标准布局（repowiki 在仓外）才误报。需要用**真实 centralized 布局**验证：成员仓 lint 应正常，共享区页面引用成员仓证据才是有边界的行为。更新脚本。
assistant: E2E **33 passed, 0 failed**，全绿。剩下的 1 个观察项（共享产品区页面引用成员仓证据 → lint 误报 `file disappeared`）是 stamp 时 `repo_path` 未持久化的工具间契约边界，非主流程 bug。收尾前再确认几个本周改动点的覆盖情况：`bootstrap.ps1` UTF-8 BOM（a4df3f0）、分析缓存相对路径（c9dea44）、install-hooks 相对路径（922a63c）、distill-worker frontmatter 分发（d66136b）。
assistant: `bootstrap.ps1.tpl` 模板本身无 BOM。查 a4df3f0（BOM 提交）到底改了哪，以及 `workspace_bootstrap.py` 写 bootstrap.ps1 时是否动态加 BOM。
assistant: BOM 修复确认正常：`_write_text` 对 `.ps1` 运行时用 `utf-8-sig` 写入，模板无 BOM 是设计使然，且有 3 个回归测试（全量 pytest 已覆盖）。`workspace.json` 结构确认只有 `wiki_layout`（无成员仓映射），印证了观察项根因。最后确认 cache.py 相对路径重构的测试覆盖。
assistant: `cache.py` 的相对路径重构（`default_cache_db`/`analysis_meta_dir`）已被 `test_index_freshness`、`test_workspace_analyzer_layout`、`test_remove_repo_cleanup` 覆盖（全量 pytest 通过）。覆盖完整。现在清理临时脚本并确认工作区状态。
assistant: `uv.lock` 只剩 1 行行尾（LF/CRLF）差异——是 `uv run` 触碰导致的噪音，恢复它；`tests/smoke_test_mcp.py` 的 4 行是我的断言修复，保留。
assistant: 测试全部完成，工作区已清理干净。下面是完整测试报告。

---

## CodeWiki MCP 整体测试报告（重点：最近一周改动）

### 测试执行情况

| 层 | 结果 | 说明 |
|---|---|---|
| **全量单元测试** | **643 passed / 2 skipped** | 覆盖全部核心改动（约 5 分钟） |
| **MCP 冒烟测试** `smoke_test_mcp.py` | **132 passed / 0 failed** | 直接调真实 handler，**修复 1 个失败** |
| **协议层 E2E**（真实 stdio client，临时脚本） | **33 passed / 0 failed** | 覆盖最近一周全部关键路径 |

### 最近一周改动逐项验证

- **多仓工作区（集中式布局，工单 01-10）**：`init_workspace` 布局闸门（首调返回 `needs_layout_decision` 且零副作用）→ 显式 `layout=colocated` 完整初始化（`workspace.json`/`bootstrap.sh`/`bootstrap.ps1`/`repo-map.md`/`schema.yaml` 全生成）→ 重复调用幂等 → **冲突布局被拒绝**。`remove_workspace_repo` 对未注册仓安全报错。✅
- **KnowledgeStore 统一存储层**：`ingest_note` → `query_wiki` 单管线落盘可检索（BM25 + authority + usage）。✅
- **P0 证据锚定**：`stamp_evidence` 盖章（frontmatter 写入 `repo://` + `content_hash`）→ `lint_wiki(stale_evidence)` 新鲜盖章 0 issue；**colocated 与 centralized 成员仓布局双场景均正常**。⚠️ 见下
- **D2 page_manifest**：`write_doc_file` 后 `.meta/page_manifest.json` 生成且记录 `source_fingerprint`。✅
- **batch_ingest 文件侧通道**：`items_file` 导入 2 条成功，返回 `report_file`。✅
- **bootstrap.ps1 UTF-8 BOM**：运行时 `utf-8-sig` 写入，3 个回归测试覆盖。✅
- **分析缓存相对路径**（c9dea44）：`default_cache_db`/`analysis_meta_dir` 的 centralized 命名空间由 `test_index_freshness`/`test_workspace_analyzer_layout`/`test_remove_repo_cleanup` 覆盖。✅
- **install-hooks 相对路径**（922a63c）：`test_install_hooks.py` 覆盖。✅
- **registry**：48 个工具齐全，含全部新工具。✅

### 发现的问题（1 个已修复 + 2 个观察项）

**① 已修复：smoke 测试过时断言**
`distill_conversation` Mode C prepare 已按 file-side-channel 改为返回 `preview` 字段（不再内联完整 `transcript`），但 `smoke_test_mcp.py` 还在断言旧字段 → 测试失败。产品功能正常，**已同步断言**（`tests/smoke_test_mcp.py` 4 行改动）。

**② 边界观察：`stamp_evidence` 的 `repo_path` 不持久化**
`stamp_evidence` 接受 `repo_path` 但证据记录里没有 repo 身份；`lint_wiki` 的 `stale_evidence` 只能从 `output_dir.parent` 猜 repo 根。主流程（colocated 及 centralized 成员仓各自的 repowiki）正常，但**共享产品区**（centralized 的 `<ws>/repowiki`）页面引用成员仓证据时会被误报 `evidence file disappeared`。属工具间契约缺口，建议后续让 stamp 持久化 repo 身份或让 lint 读 `workspace.json`。

**③ 观察项：版本号漂移**
`codewiki/mcp/server.py` 硬编码 `version="5.2.1"`，与 `pyproject.toml` 的 `5.5.1` 不一致（MCP `initialize` 返回的版本会误导客户端）。

### 工作区状态
- 仅保留 `tests/smoke_test_mcp.py` 的断言修复；临时 E2E 脚本已删除，测试期间 `init_workspace` 误写到工作区根的产物已全部清理。

---

按项目知识沉淀规则，①的教训（MCP 子进程 cwd 不随 `os.chdir` 变化——本次 E2E 踩坑导致工作区被污染）和②的发现值得记录为 Wiki 笔记。需要我把这两条整理成笔记草稿供你确认吗？
