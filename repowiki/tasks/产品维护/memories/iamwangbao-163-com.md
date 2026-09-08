### 2026-08-28 12:16

用户询问 .meta/telemetry/Administrator.jsonl.tmp.19748 孤儿临时文件来源与清理时机：根因是 telemetry.py 的 _atomic_write_lines 崩溃安全写入（临时文件+os.replace）在进程被强杀/崩溃/断电或抛非 OSError 异常时残留；无自动清理机制，不影响 aggregate_usage（glob *.jsonl 不匹配），手动删除即可。

### 2026-08-28 12:16

用户在该会话中报告 codewiki get_task_context 调用很慢，需定位性能瓶颈原因（raw 捕获不完整，仅 user 消息无 assistant 回复，问题转主 Agent 跟进）。

### 2026-09-04 16:17

2026-09-04：D19 锁文件集中化变更完成 review（7 文件 +109/−13，`store.py` 新增 `_lock_path_for()` 将 `.lck` 从目标旁边车迁到 `<wiki-root>/.meta/locks/<sha256(abs)[:20]>.lck`，无 `.meta` 祖先时回退就地 sidecar）。结论：代码质量良好，可直接提交，无必须修改项。

### 2026-09-04 16:17

2026-09-04：D19 相关测试全绿——`tests/test_phase2_concurrency.py` 16 passed（含新增 3 个），加 test_locks/knowledge_store/layout_routing/phase3_4/phase4_second_slice 共 63 passed，合计 79 passed（Windows / Python 3.14.5）；新增跨进程测试真实起 2 个 subprocess 各 +15 断言 =30 且仅 1 个锁文件，证明集中锁与旧实现互斥等价。

### 2026-09-04 16:17

2026-09-04：针对 `.meta/locks/` 锁文件累积问题，用户已拍板选「仅 Windows 释放即删」方案——下一步是在 `store.locked()` 出口做 best-effort unlink（吞错），Unix 因 inode race 保留不删，并在 `locks.py`/docstring 注明原因，约 10 行 + 测试。实现时务必只改 sidecar 语义的 `store.locked()`，不要下沉到 `file_lock` 通用层（`wiki_index`/`workspace_bootstrap` 锁的是数据文件本身）。

### 2026-09-04 16:17

2026-09-04：评估后否决了 `lint_wiki` 补刀清扫锁文件——锁文件存在是常态非问题（只能 fix-only 不能当 check 上报），Unix 下同样踩 inode race，且释放即删生效后残留量被钉死在上界，补刀收益极低。

### 2026-09-04 16:17

2026-09-04：D19 review 记录的非阻塞观察（未处理）：`_lock_path_for()` 每次调用做 resolve+祖先遍历+mkdir（低频可接受，热点可加「root→locks_dir」缓存）；Windows 下路径大小写不同会导致哈希不同、锁不互斥（内部路径已归一化，风险极低）；升级窗口内新旧进程锁路径不同、互不互斥，升级须重启 server。

### 2026-09-05 19:12

回答了用户关于 `MCP_Tools_DocWriter.md` frontmatter `sources` 生成与使用的提问：梳理出「`schema.yaml` 的 `auto_evidence` 开关 → `write_doc_file` 落盘后 `_inject_evidence` → `append_evidence_block` 外科插入」的自动盖章链路，及其唯一消费者 lint 的 `stale_evidence`；实测本页两条证据（gen/tpl）重算哈希与记录一致，当前状态 `ok`，lint 不会报警。同时厘清了 `sources` 的三个生产者与四类同名歧义。

### 2026-09-05 19:12

上一轮补蒸馏产出的 3 条草稿笔记处置结果：笔记 1（锁文件清理采用「仅 Windows 释放即删」，Unix 一律保留不删）与笔记 3（D19 锁文件集中到 `<wiki-root>/.meta/locks/<sha256(目标绝对路径)[:20]>.lck`）已由用户确认为 `stable`；笔记 2（`file_lock` 的锁文件可能是数据文件本身，释放即删只能加在 `store.locked()`，不能下沉到通用 `file_lock`）仍为 `draft`，待用户 `confirm_note` 或 `reject_note`。

### 2026-09-05 19:12

挂起待办（未实现）：「仅 Windows 释放即删」约 10 行 + 测试，只改 `store.locked()` 出口做 best-effort unlink 并吞掉异常；原因是 Unix 存在 inode race（等锁方持有旧 inode fd，unlink 后新进程开新 inode，互斥失效导致丢更新）。已否决的替代方案：用 lint_wiki 补刀清理锁文件（理由：锁文件存在是常态非问题、只能 fix-only 不能当 check、Unix 同样踩 race、收益极低）。

### 2026-09-05 19:12

核对 `docs/articles/CodeWiki-Plus系列11：机器写的Wiki凭什么可信——证据、保鲜与冲突消解.md` 对 `sources` 生成与 `stale_evidence` 的覆盖：文章第二节「落盘时」与第五节「证据漂移」已覆盖设计意图（内容哈希 vs git SHA、单页上限 8、不覆盖人工证据、只提醒不改写），但缺 6 条实现边界（sources 是采样锚点存在覆盖率缺口、三生产者区分、多仓 `evidence_roots` 解析、warning 级别只扣 3 分、无行号退化为整文件哈希、注入须在 `_record_page_manifest` 之前）。已向用户提议把这些补写成文档或一条 architecture 笔记，**用户尚未答复**；文章 78 行「被频繁检索命中复核提醒顺延」未核实（属 `stale_notes` 检查）。

### 2026-09-05 19:12

候选 lesson 笔记「蒸馏 subagent 自报的笔记状态不可信，需用 `get_task_context` 的 `related_notes[].status` 复核」已向用户提议写入 Wiki，**用户尚未答复**；本次蒸馏已将其作为 `draft` 笔记产出，等待确认闸门。本轮「产品维护」补蒸馏（1 条 raw，11 轮）完成，产出 5 条 draft 笔记 + 5 条任务记忆，pending raw 归零。

### 2026-09-07 14:49

2026-09-07 会话（source_session 993f1c39697248b4a2c07b3edec98972）提出并定案 MCP 层中文返回文本的 i18n：YAML 双文件全量（`codewiki/mcp/locales/zh.yaml` 为源、`en.yaml` 全量覆盖）、一次性全做、无运行时回退（缺 key 返回哨兵，靠发版前 key 集一致性测试暴露）、范围含 prompt 元数据 + 22 个正文 + instructions + resources + 工具层散点 + 落盘产物。

### 2026-09-07 14:49

审计结论（已核对）：工具 schema description 与错误消息全部为英文，中文 i18n 工作量不含这部分；中文集中在 prompts.py（正文约 1250 行 + 元数据约 100 行）、resources.py catalog（约 92 行）、server.py instructions（57 行）、工具层散点几十行，合计约 1500 行需英文创作。

### 2026-09-07 14:49

语言来源定案：`~/.codewiki/config.json` 的 lang 字段 > `CODEWIKI_LANG` 环境变量 > 系统 locale 推断 > 兜底 zh；不能放项目级 `repowiki/schema.yaml`（MCP server 启动期无 repo 上下文）。用户侧切换语言的方式是在 MCP 配置里加 `"env": {"CODEWIKI_LANG": "en"}`。

### 2026-09-07 14:49

M1 基建已落地：新增 `codewiki/mcp/i18n.py`（`t()` / `current_lang()` / lru_cache 加载 locales）、`codewiki/mcp/locales/zh.yaml` 与 `en.yaml`；`codewiki/mcp/server.py` 已接线（i18n 导入 + Server 构造前初始化语言 + instructions 改为从语料取）；`pyproject.toml` 的 wheel artifacts 已加入 locales 资源。

### 2026-09-07 14:49

`tests/test_i18n.py` 已建立（key 集一致性、占位符一致性、缺 key 哨兵、语言解析优先级四组断言），尚未运行验证是否全绿。

### 2026-09-07 14:49

待办（未开始，按依赖顺序）：(1) prompts.py 22 个 Prompt 的 title/description 接入语料；(2) 22 个 `_prompt_*` 正文函数重写为「按语言取模板片段 + 保留逻辑」并产出英文版（约 1250 行创作，本次最大工作量）；(3) resources.py 的 `prompts/catalog` 改为从 `list_prompts` 派生（消除 15 vs 22 漂移）；(4) 工具层中文散点；(5) 落盘产物（agents_md / wiki_index / reading_guide / schema_generator）语言跟随；(6) `tool_count` 改运行时计数、instructions 里 11→22 修正。

### 2026-09-07 14:49

风险提示：英文正文初稿由 Agent 创作，定案时建议合入前做一次面向英文可读性的审校，避免机器直译风格拉低产品完成度。
