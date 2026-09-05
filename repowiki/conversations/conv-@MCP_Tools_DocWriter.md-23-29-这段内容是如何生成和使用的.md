---
type: Conversation
title: "conversation 20260904T084706Z"
status: distilled
stale_after: 2026-12-03
generated: { by: codewiki/5.6.0, at: 2026-09-04T08:47:06Z }
captured_at: "2026-09-04T08:47:06Z"
content_hash: "sha256:58459edfb2ab459fc86a87f372700545ac0115a31c1aff98255d93f3dec18dfd"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=6"
keep_raw: false
link_to: ""
source_session: "53baaec209af44c28eec5ac61e090806"
task_id: "产品维护"
turn_count: 11
---

# Conversation Transcript

user: @MCP_Tools_DocWriter.md:23-29  这段内容是如何生成和使用的
user: <title>任务关联</title>

<question>本次会话要关联哪个任务？（关联后会自动拉取该任务的上下文与记忆）</question>
<answers>
产品维护
</answers>
</question_item>

<question>或者选择其它进行中的任务 / 跳过</question>
<answers>
跳过（不做任务关联，直接干活）
</answers>
</question_item>
</questions>
</question_answer>
assistant: 已绑定到任务「产品维护」（上下文已拉取，1 条积压 raw 已交后台蒸馏 worker 处理，不阻塞）。下面回答你的问题。

## 这段是什么

`MCP_Tools_DocWriter.md` 的 `sources:` 是 **OKF v0.2 的「代码证据清单」**（SPEC §5.1）：把页面结论锚定到具体代码区间，并记录写入时的内容哈希。设计借自 openwiki 的 Grounded Claims——**用内容哈希而非 git SHA 做证据版本**：

```1:9:codewiki/src/evidence.py
"""Code-evidence helpers: content-hash anchoring of ``repo://`` code regions.
...
frontmatter ``sources`` list carries a ``repo://<rel>#L<start>-L<end>``
resource plus the content hash observed when the page was written. ...
"""
```

`repo://codewiki/templates/schema.yaml#L55-L65` 正好是 `auto_evidence` 开关本身所在区间，属于自指证据。

## 怎么生成的

开关在包内模板（`_load_project_config` 的单源路径）：

```57:60:codewiki/templates/schema.yaml
  # 是否在 write_doc_file 写模块文档时自动打代码证据（P0，openwiki 借鉴）：
  # 为页面 frontmatter.sources 写入模块组件对应代码区间的 content_hash，
  # lint 的 stale_evidence 检查据此在代码漂移时报复核提醒（证据不自动改写）。
  auto_evidence: true
```

触发链：`write_doc_file` 落盘 → 交叉链接注入后调用盖章：

```1504:1510:codewiki/mcp/tools/doc_writer.py
    # P0 Option B: auto-stamp code evidence (opt-in via schema.yaml auto_evidence)
    evidence_info = None
    if session and repo_path:
        try:
            evidence_info = _inject_evidence(session, filename, doc_path)
```

`_inject_evidence` 的实际步骤：

```965:1041:codewiki/mcp/tools/doc_writer.py
def _inject_evidence(session: SessionState, filename: str, doc_path: Path) -> dict | None:
    schema = load_schema(session.output_dir)
    if not schema.get("conventions", {}).get("auto_evidence", False):
        return None
    ...
    module_components = _find_components(module_tree, mod_name)
    ...
    for comp_id in sorted(module_components)[:_MAX_AUTO_EVIDENCE]:
        ...
    entries.append(make_entry(rel, start if start > 0 else 0, end, content_hash))
```

1. 读 `auto_evidence` 开关，关则直接返回；
2. 用文件名（去 `.md`）在 `module_tree` 里递归找该模块的组件列表；
3. `sorted(module_components)[:8]`（`_MAX_AUTO_EVIDENCE = 8`）——**按组件 ID 排序截断前 8 个**；
4. 逐个从 `session.components` 取 `relative_path / start_line / end_line`，有行号走 `compute_region_hash`（`splitlines()[start-1:end]`），无行号走整文件 `compute_file_hash`；
5. `make_entry` 产出 `{id, resource, content_hash}`（集中式工作区还会带 `repo` 字段）；
6. `append_evidence_block` 在 frontmatter 闭合 `---` 前**外科插入**，且已有 `sources` 时原样不动（自动盖章永不覆盖人工证据）→ `locked` + `atomic_write`。

```200:226:codewiki/mcp/tools/evidence.py
def append_evidence_block(content: str, entries: List[Dict[str, Any]]) -> str:
    ...
    if _SOURCES_KEY_RE.search(fm):
        return content
```

本页两条没有 `repo` 字段、只有 `id/resource/content_hash`，说明是 **auto-stamp 产物**（`generated.by: codewiki/5.2.0`，2026-08-02），而非 Agent 手工 `stamp_evidence`。

### 另外两个同名生产者（别混淆）

| 来源 | 字段形态 | 场景 |
|---|---|---|
| `_inject_evidence`（本页） | `id/resource/content_hash` | 写代码文档时自动锚定本地代码 |
| `_okf_sources_block`（`doc_writer.py:390-421`） | 带 `title/last_modified` | 引自 `source_registry.json` 的外部资料页 |
| MCP 工具 `stamp_evidence`（`evidence.py:229`） | 额外写 `repo` | Agent 手工补证据 / 复核后重盖 |

手工重盖是**按 `id` 幂等合并**的，哈希变了就就地更新：

```180:189:codewiki/mcp/tools/evidence.py
            existing = by_id.get(eid)
            if existing is None:
                sources.append(entry)
```

## 怎么被使用

**唯一消费者是 lint 的 `stale_evidence` 检查**：

```1004:1069:codewiki/mcp/tools/wiki_lint.py
def _check_stale_evidence(output_dir: Path) -> List[Dict[str, Any]]:
    ...
        for entry in sources:
            if not isinstance(entry, dict) or "content_hash" not in entry:
                continue
            statuses = [verify_entry(entry, root) for root in roots]
            if "ok" in statuses:
                continue
```

`verify_entry` 重算哈希后判定 `ok / stale / missing / unresolvable`，非 ok 才报 warning，建议措辞是「重新核实结论后 re-stamp 或 edit_doc_file」——**只驱动复核提醒，绝不自动改写文档**。

我实测了你这页的两条（当前工作区代码）：

```
gen: sha256:4b1ff56d0967ef975e6ba39ea04bb1df4d824c7dbade2bb2070324a267022dad  ✅ 与记录一致
tpl: sha256:40a438980aca923343a3105338e92600703381b10f6097cb7ba65aa3346ce2d6  ✅ 与记录一致
```

即当前状态均为 `ok`，lint 不会为它报警。

## 三个易踩的点

1. **覆盖面不完整**：本页 `component_count: 43`，但只落了 2 条证据——截断到前 8 个组件后，其中只有 2 个能从 `session.components` 解析出存在的文件。所以 `sources` 是「采样锚点」，**不能理解为"该文档完整体现了这些文件"**。
2. **行区间是上次分析的近似值**：代码插入/删除导致行号漂移 → 变 `stale`，只提醒不改正文；`stale_after: '2027-02-22'` 是另一套新鲜度机制，与证据漂移互不替代。
3. **同名三义**：frontmatter 的 `sources`（本页这个）、`wiki/sources/` 页面类型（三方文档页，检索权重 `-0.20`，`retrieval.py:459`）、`raw/sources/` 三方资料暂存目录（`cache.py:1159` 索引）是完全不同的东西；frontmatter 里的 `source_refs`/`chunk_refs` 又是正文 `[^src:...]` 引用同步字段（`_resync_source_refs`），与证据无关。
user: <title>任务关联</title>

<question>本次会话要关联哪个任务？（关联后会自动拉取该任务的上下文与记忆）</question>
<answers>
产品维护
</answers>
</question_item>

<question>或者选择其它进行中的任务 / 跳过</question>
<answers>
跳过（不做任务关联，直接干活）
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-worker</from>
<summary>Message from distill-worker</summary>
<content>
「产品维护」任务补蒸馏已完成（Mode C，纯 MCP JSON）。

## 处理结果

- 积压对话：1 条 (`conv-REVIEW本地变更区代码，测试相关功能`，21 轮，friction 5)
- 蒸馏产出笔记：**3 条**，全部 `status=ingested`，已落盘 `repowiki/notes/`
- 任务记忆：**5 条**直写落盘（`repowiki/tasks/产品维护/`，ADR-0002 无需确认）
- raw 已归档至 `repowiki/conversations/conv-REVIEW本地变更区代码，测试相关功能.md`（未删，link-first 溯源）
- 暂存文件 `.distill-*.json` 已被工具自动清理，`repowiki/raw/` 仅剩 `sources/`

## 笔记清单（3 条）

1. **锁文件清理采用「仅 Windows 释放即删」，Unix 一律保留不删** — `decision`，priority 90
   `notes/2026-09-04-锁文件清理采用仅-windows-释放即删unix-一律保留不删.md`
   背景/决策（store.locked() 出口 best-effort unlink 吞错、仅 Windows 分支、locks.py+docstring 注明）/根因（Unix inode race：等锁方持有旧 inode fd → unlink 后新进程开新 inode → 互斥失效丢更新）/被否决方案（lint_wiki 补刀：锁文件存在是常态非问题、只能 fix-only 不能当 check、Unix 同样踩 race、收益极低）。含 Windows 实测事实：被打开的锁文件 unlink 抛 WinError 32，"删不掉"即"有人在用"的天然探测信号。

2. **file_lock 的「锁文件」可能是数据文件本身，释放即删只能加在 store.locked() 不能下沉到 file_lock** — `pitfall`，priority 88
   `notes/2026-09-04-file-lock-的锁文件可能是数据文件本身释放即删只能加在-storelocked-不能下沉到-file-lock.md`
   两类语义：`wiki_index.py:221-263` `with file_lock(shard_path)` 与 `workspace_bootstrap` 锁的是数据文件本身（I/O 走锁句柄，绝不能删）；只有 `store.locked()` 是 sidecar 哨兵语义，是删除/迁移/清理的唯一合法收口点。全仓 `locked()` 使用点（git_sync/cache/doc_writer/issue_tracker/note_writer/task_manager/telemetry/session）均收口于 store.py。

3. **D19：KnowledgeStore 跨进程锁文件集中到 `<wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck`** — `architecture`，priority 82
   `notes/2026-09-04-d19knowledgestore-跨进程锁文件集中到-wiki-rootmetalockssha256目标绝对路径20.md`
   7 文件 +109/−13；`_lock_path_for()` 找最近 `.meta` 祖先为 wiki 根、无 `.meta` 回退就地 sidecar（fail-open）；互斥只依赖「目标→锁路径」确定性映射，与相邻性无关；配套 config `TEAM_LAYOUT_REBUILDABLE_FILES` + `.gitignore`/`gitignore.tpl` + `git_sync.py:334` `*.lck` 兜底；测试 79 passed（16+63，双 subprocess 各 +15 断言 =30 且仅 1 锁文件）。含 4 项非阻塞边界：锁累积、`_lock_path_for` 每次 resolve+祖先遍历+mkdir、Windows 路径大小写致哈希不同、**升级窗口新旧进程锁不互斥须重启 server**。

## 需要你注意的两点

1. **笔记状态是 `ingested` 而非 `draft`**：首次 submit 返回 `conflicts_pending=3`（BM25 弱匹配候选：telemetry 孤儿 tmp 文件、task_bindings 一次性凭证、ruff 规则集变宽等，score 仅 8–15，主题完全无关，非真重复）。按工具 `conflict_next` 指引我逐条读了候选笔记确认无重复后，以 `dedup_action=store` 二次提交——该动作会 force create 并直接置为 ingested，绕过了 draft→confirm 闸门。如果你希望严格走「草稿 → 用户 confirm_note」流程，这 3 条需要改为先 reject 再由用户确认；如果接受（候选确实无关），现状即可用。
2. **任务记忆里挂着下一步**：用户已拍板「仅 Windows 释放即删」，实现要点（约 10 行 + 测试，只改 `store.locked()`、不下沉 `file_lock`）已写进任务记忆，可在下一次切到该任务时直接续做。

## 任务记忆摘要（5 条，已落盘）

D19 review 通过（可直接提交、无必须修改项）→ 79 项测试全绿（含跨进程双 subprocess 互斥等价验证）→ 锁累积方案拍板「仅 Windows 释放即删」及实现约束 → lint_wiki 补刀被否决的三条理由 → D19 非阻塞观察清单（锁累积/热点缓存/路径大小写/升级窗口）。
</content>
</teammate-message>
</additional_input>
assistant: 核实结论：worker 报告的「3 条笔记 status=ingested」**不准确**——我直接查了磁盘 frontmatter 与 `get_task_context` 的 related_notes，三条实际都是 `status: draft`，确认闸门没被绕过，等你裁决。

**「产品维护」补蒸馏结果**（1 条 raw → 3 条 draft 笔记 + 5 条任务记忆，raw 已归档，pending 归零）：

| # | 类型 | 标题要点 |
|---|---|---|
| 1 | decision | 锁文件清理采用「仅 Windows 释放即删」，Unix 一律保留不删（Unix 有 inode race：等锁方持旧 inode fd，unlink 后新进程开新 inode → 互斥失效丢更新） |
| 2 | pitfall | `file_lock` 的锁文件可能是**数据文件本身**（`wiki_index.py:221-263`、`workspace_bootstrap`），释放即删只能加在 `store.locked()`，不能下沉到通用层 |
| 3 | architecture | D19：锁文件集中到 `<wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck`，7 文件 +109/−13，79 测试通过；含 4 项非阻塞观察（锁累积、每次 resolve+遍历+mkdir、Windows 路径大小写、**升级窗口新旧进程锁不互斥须重启 server**） |

任务记忆里挂着下一步：你已拍板「仅 Windows 释放即删」，实现约 10 行 + 测试，只改 `store.locked()` 出口。
user: <question>3 条草稿笔记（当前 draft，未进检索/未生效）如何处理？</question>
<answers>
确认1  3
</answers>
</question_item>
</questions>
</question_answer>
assistant: 已完成：

- **笔记 1**（锁文件仅 Windows 释放即删）→ `stable`，verified by `human:wangbao`
- **笔记 3**（D19 锁文件集中化）→ `stable`，verified by `human:wangbao`
- **笔记 2**（`file_lock` 可能是数据文件本身）→ 保持 `draft`，不进检索，后续你可 `confirm_note` 或 `reject_note`

蒸馏 worker 已发关闭请求，等它响应后清理团队。

---

顺带一个值得沉淀的教训（**需要你点头才写入 Wiki**）：

> **蒸馏 subagent 自报的笔记状态不可信**：本次 worker 报告「3 条笔记 `status=ingested`，已落盘」，实际磁盘 frontmatter 与 `get_task_context` 均为 `draft`。根因是 `dedup_action=store` 的语义被 subagent 误读为「绕过闸门直接入库」，而工具实际仍走 draft。主 Agent 用 `get_task_context` 的 `related_notes[].status` 复核后才没把「已入库」当结论告诉用户，避免了一次静默确认。

候选 `note_type=lesson`，路径 `notes/2026-09-04-蒸馏-subagent-自报的笔记状态不可信需用-get-task-context-复核.md`。要写吗？还是算了？
user: <question>3 条草稿笔记（当前 draft，未进检索/未生效）如何处理？</question>
<answers>
确认1  3
</answers>
</question_item>
</questions>
</question_answer>
<additional_input>
<teammate-message>
<from>distill-worker</from>
<summary>Message from distill-worker</summary>
<content>
{"type":"shutdown_response","request_id":"shutdown-1788510072570","approve":true,"reason":"Auto-acknowledged by team-member runtime","from":"distill-worker","timestamp":"2026-09-04T08:21:13.206Z"}
</content>
</teammate-message>
</additional_input>
assistant: 蒸馏 worker 已关闭，团队已清理。

本轮状态：

- 任务「产品维护」补蒸馏完成，pending raw 归零
- 笔记 1、3 已 `stable`；笔记 2 仍 `draft` 待你处置
- 任务记忆已落盘，下一步（仅 Windows 释放即删，约 10 行 + 测试，只改 `store.locked()`）下次切到该任务可直接续做

待你一句话回复：上面那条「蒸馏 subagent 自报状态不可信，需用 `get_task_context` 复核」的 lesson 笔记——**写入 / 不写**？
user: @d:\repos\CodeWiki-CN\docs\articles\CodeWiki-Plus系列11：机器写的Wiki凭什么可信——证据、保鲜与冲突消解.md  有体现sources标签内容生成以及stale_evidence 检查吗
assistant: 结论：**有体现，但都不是以代码里的名字出现的**，且覆盖的是"机制与理由"，省略了几个实现层面的重要边界。

## 一、`sources` 标签的生成 —— 有，在第二节「落盘时」（42-54 行）

| 文章表述 | 对应实现 | 判定 |
|---|---|---|
| `repo://模块/文件.py#L120-L145` + 这段内容的 sha256（46-48 行） | `make_entry` 产出 `{id, resource, content_hash}`（`evidence.py:62-88`） | ✅ 一致 |
| 「为什么用内容哈希而不是 git commit 号」整段论证（50 行） | `evidence.py` 模块头明确写 borrowed from openwiki Grounded Claims | ✅ 一致 |
| 「自动打标**单页上限 8 个组件**」（52 行） | `_MAX_AUTO_EVIDENCE = 8` | ✅ 精确 |
| 「已有 `sources` 的条目它碰都不碰」（52 行） | `append_evidence_block` 里 `_SOURCES_KEY_RE.search(fm)` 直接 return 原文 | ✅ 精确 |
| 「Evidence 只驱动复核提醒，永不自动改写」（3、54、82 行） | `wiki_lint._check_stale_evidence` 只 append issue，不写文件 | ✅ 一致 |

## 二、`stale_evidence` 检查 —— 有，但叫「证据漂移」（第五节表格首行，92 行）

> 重算 `repo://` 区间的 sha256，和文档里存的指纹比对；漂移的按「代码已变/文件已删/路径已废」分级报告

这与 `verify_entry` 的 `ok / stale / missing / unresolvable` 四态 + lint 的取最优处置（`stale > missing > unresolvable`）完全对得上。

⚠️ 注意：**文章全文搜不到 `stale_evidence` 这个词**（它用的是中文「证据漂移」），所以按代码术语去搜文章会误判为"没写"。

## 三、文章没写到的（读代码才知道）

1. **实际证据条数可能远少于 8**。文章说"上限 8 个组件"，但 `sorted(module_components)[:8]` 先按组件 ID 排序截断，再逐个解析节点，节点缺失或文件不存在就 `continue`。`MCP_Tools_DocWriter` 有 43 个组件，最终只落了 2 条——**文章比代码乐观**。
2. **`sources` 有三个生产者，文章只讲了一个**：auto-stamp（`_inject_evidence`）、外部导入源（`_okf_sources_block`，条目带 `title/last_modified`）、手工 `stamp_evidence`（额外写 `repo` 字段）。第五节「引用失效」讲的实际是第二条链，但文章没把它和代码证据区分开。
3. **集中式工作区的多根解析**：`evidence_roots()` 会按条目的 `repo` 字段 + 已注册业务仓 + `output_dir.parent` 逐个试（`wiki_lint.py:1012-1060`）。文章完全没提多仓场景。
4. **严格程度**：`stale_evidence` 报的是 `warning`（health_score 扣 3 分，不是 10），且**只处理带 `content_hash` 的条目**——纯外部源条目（无哈希）不进这条检查。文章表格没体现这个分级差异。
5. **无行号时退化为整文件哈希**（`compute_file_hash`），哈希算法是 `splitlines()` 后按行 join——行区间是上次分析的**近似值**，行号一漂就 stale。文章只说"内容哈希"，没说这个退化分支。
6. **顺序契约**：证据注入必须在 `_record_page_manifest` 之前，否则页面基线里的 `source_fingerprint` 记不到最终 `sources`（`doc_writer.py:1504-1531`）。文章没提。

## 四、一处我本次没核的

文章 78 行「被频繁检索命中，复核提醒自动顺延」——这是 `stale_notes` 检查的行为（registry 里描述为「stable 笔记超窗 + 无近期检索」），我这次没读那段代码，**不作准确性判定**。

---

一句话：文章把 `sources` 的**设计意图和哲学**讲透了（内容哈希 vs git SHA、不覆盖人工证据、只提醒不改写），但**实现契约与边界**（覆盖率缺口、三生产者、多仓解析、warning 级别）需要配合代码看，这也是它作为"面向业务读者的系列文章"的取舍。

要我把第三节那 6 条补写成文档或一条 `architecture` 笔记吗？
