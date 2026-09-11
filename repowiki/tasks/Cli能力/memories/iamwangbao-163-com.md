### 2026-09-10 22:11

## 2026-09-10 CLI 能力增强方案（grill-me 四轮后归档，暂缓）

用户原始诉求：「CLI 能力弱、没和 MCP 对齐，增强后更省 token」。追问后重构为：收益来源是 **MCP 工具定义每轮常驻**，不是输出体积也不是往返次数。

**实测数据**：`get_all_tools()` 载荷 88,727 字符 / 49 工具（≈22k-35k token 估算）；`codewiki --help` 915 字符；CLI 12 个动词 vs MCP 49 个工具。

**收敛结论**：
- 三层模型：披露层(skill/command) → 执行层(CLI) → 后端(MCP 可开关)
- 「完善 CLI」本身不产生收益，它只是让「关掉 MCP」可行
- 路径 B（渐进式披露）由用户提出，常驻 ~100 词/skill，优于我最初的路径 A（收缩暴露面 ~6-8k）
- IDE 已原生支持全部开关：`~/.codebuddy/mcp.json` per-server disabled、`mcp-disabled-tools.json` per-tool、skill `disable`、command `disable-model-invocation` → **不需要改 registry**
- 排除：49 个 skill 一对一映射（常驻 7-15k 与 A 打平 + 丢 schema 校验 + 触发竞争 + 放弃工作流粒度）；手写 49 个 CLI 命令（三份维护）；命令清单进 AGENTS.md

**归档位置**：`docs/plans/cli-capability-progressive-disclosure.md`（Status: deferred，含已 settle D1-D4、未 settle O1-O6、被排除候选及原因、可信度边界）

**恢复条件**：先拿实测数——`/context all` 看 MCP 真实 token，或 A/B 跑两遍比 `/cost`。判定线：差值接近 22k-35k/轮则继续；仅 2-3k 则整个前提推翻、收手不做。

**卡住的认知**：目前除 88,727 字符外全是估算，包括官方「100 词」在中文下的真实 token。在实测前不要再拿这些数字推进设计。

### 2026-09-10 22:30

## 2026-09-10 第一刀已落地：AGENTS.md 移除 QwenWork 块

- 删除 `<!-- CODEWIKI-QWENWORK:START/END -->` 块（1,222 字符），**未改任何生成器代码**。AGENTS.md 10,175 → 8,952 字符（-12.0%），214 → 186 行。
- 链路已验证：`upsert_agents_section` 连调两次均返回 False（幂等），QWENWORK 标记未回冲，TEAM-MEMORY-TASK / CodeWiki LLM Wiki 两块不变。不回冲依据：`upsert_qwenwork_protocol` 仅在 `wiring == "prompt"` 分支调用（`cli/utils/ide_config.py:315-318`）。
- 可逆：QwenWork 用户重跑 `--ide qwenwork` 接线即自动写回。
- 测试：`tests/test_install_hooks.py` + `test_strip_system_injection.py` 共 46 passed。
- 未做：第二刀（Task memory 剧本 32% 外移到 MCP prompt `task-workflow`）、第三刀（Wiki 块 34% 与 MCP 工具描述去重）——待用户定案 R6-Q2/Q3。

**关键约束（后续别踩）**：AGENTS.md 79% 由生成器托管，改文件本身会被 `install-hooks`/`generate` 覆盖，持久改动必须改模板或常量。本刀之所以能只改文件，是因为 QwenWork 块只在 prompt 模式写入。

### 2026-09-10 22:54

## 2026-09-10 第二刀已落地：Task memory 段精简 + 剧本外移（改生成器）

- `codewiki/mcp/prompts.py:40` `_TASK_MEMORY_AGENTS_SECTION` 3,286 → 836 字符（-74.6%）。保留 5 条运行时铁律（弹框只弹一次/一框列全、set_session_task 绑定、get_task_context、补蒸馏委托 subagent 不阻塞、草稿须 confirm_note 而记忆直写 ADR-0002）；存储布局与实现约束外移到同文件 `_prompt_task_workflow`（MCP prompt `task-workflow`）新增段，内容不丢；AGENTS.md 段尾加 `get_prompt(name="task-workflow")` 指针。
- 联动：该常量同时被 prompts.py 两处安装/卸载指令引用，一处改全处生效，无第二真相。
- 本仓库 AGENTS.md 已刷新：10,175 → **6,473 字符（-36.4%）**；upsert 第一次 True（替换）、第二次 False（幂等）。
- 全量 pytest：924 passed, 2 skipped。
- 未做第三刀：Wiki 块（3,499 字符，i18n 文案在 `locales/{zh,en}.yaml` 的 `artifacts.agents_md.main`）与 MCP 工具描述去重——**依赖 P1（MCP 描述瘦身）先定「信息归谁」，顺序不能反，否则可能删掉两边都没有的信息**。
- `_QWENWORK_CAPTURE_SECTION`（933 字符）保持不动：只在 prompt 模式注入，是千问办公的协议正文。

### 2026-09-11 06:53

Cli能力方案已归档到 docs/plans/cli-capability-progressive-disclosure.md（Status: deferred），含 Problem（49 工具 vs 12 动词、88,629 字符实测、CLI 缺 --json 与 est_tokens 渲染）、三层模型（披露层 skill/command → 执行层 CLI → 后端 MCP 可开关）、已 settle D1–D4 与未 settle O1–O6、被排除候选及原因、恢复条件（A/B 实测每轮差值接近 22–35k 就继续，只有 2–3k 就整个推翻收手）。

### 2026-09-11 06:53

实测拆解（2026-09-10）：MCP tools/list 88,629 字符 = 工具 description 44% + 参数 description 26% + enum 2% + 结构开销 28%；CJK 仅 20 字符→「中译英」无收益；Top 8 占 33%，Bottom 15 仅 13.5% → 先瘦身大工具描述，砍工具数量性价比最差。

### 2026-09-11 06:53

第一刀：删除本仓 AGENTS.md 的 CODEWIKI-QWENWORK 块，10,175 → 8,952 字符（-12%）；验证 upsert 连续两次返回 False、标记未回冲（该块只在 wiring=prompt 分支写入，hook 模式不回冲），tests/test_install_hooks.py + test_strip_system_injection.py 46 passed。

### 2026-09-11 06:53

第二刀：codewiki/mcp/prompts.py 的 _TASK_MEMORY_AGENTS_SECTION 从 3,286 精简到 836 字符（-74.6%），保留 5 条运行时铁律，存储布局/压缩阈值/分层有界等细节外移到同文件 _prompt_task_workflow（MCP prompt task-workflow），段尾加 get_prompt("task-workflow") 指针；本仓 AGENTS.md → 6,473 字符（-36.4%），全量 pytest 924 passed / 2 skipped。

### 2026-09-11 06:53

第三刀（Wiki 块 3,499 字符与 MCP 38,980 字符工具描述去重）暂缓：需先做 P1（MCP Top 8 工具描述瘦身）定下「信息归谁」，否则可能删掉另一边也没有的信息。

### 2026-09-11 06:53

阻塞项/待办：telemetry（repowiki/.meta/telemetry/*.jsonl）只有 hit/by_file/adopted 三种记录，没有 MCP 工具调用数据 → 「按频次选 core 面 / 工具调用量排名」目前无数据支撑；token 估算 injection_budget.py 用 chars/4，中文档案严重低估，/context all 或 /skills 的真实 token 数用户尚未提供。

### 2026-09-11 09:56

## 2026-09-11 子代理 MCP 授权修复 + 两个新发现

**修复**：`.codebuddy/agents/distill-worker.md:9-10` 的 `tools: ReadFile` + `toolsMCP: codewiki` 改为 `mcpServers:\n  - codewiki`（去掉 tools 白名单，改为继承）。依据：官方文档子代理字段是 `mcpServers`（可引用全局已连接 server），**没有 `toolsMCP` 这个字段**；且 `tools` 是白名单，会挡掉 MCP。

**验证**：改前 spawn 该 worker = 0 tool uses 空转；改后 = 2 tool uses，`distill_conversation(mode="prepare", task_id="Cli能力")` 成功返回 `status=noop`。

**发现 1（子代理侧）**：worker 报 `mcp_get_tool_description` 返回 `Server 'codewiki' not found or not connected`，但 `mcp_call_tool` 直调成功 → 描述查询通道异常、调用通道正常。worker 靠剧本里硬编码的工具名工作，所以不受影响，但这本身是缺陷。

**发现 2（归属丢失，更重要）**：本会话捕获的 raw `repowiki/raw/conv-manually_attached_skills-*.md` frontmatter **没有 task_id**，而 `repowiki/.meta/task_bindings/c9253615a4a04beb97dbc506d1c2bfe7.json` 已被删除（绑定被消费）。结果：会话开始提示「任务 Cli能力: 1 条积压」，但按 task_id 查是 0 条——归属丢失且绑定是一次性凭证，不可恢复。疑似捕获路径消费了绑定却没把 task_id 写进 frontmatter。

### 2026-09-11 10:35

## 2026-09-11 归属丢失漏洞：已定位、已复现、已修复

**先证伪了自己的假设**：受控实验（绑定在/不在 × 首次/重捕 4 场景）显示 `binding → task_id` 链路**全部正确**，所以「绑定消费导致归属丢失」不是根因，没有盲改。

**真漏洞（可复现）**：`绑定已消费` + `旧 raw 已被蒸馏移除（文件删除 + 索引条目移除）` → 同会话再次捕获时，supersede-inherit 只看 pending 条目，找不到可继承对象 → **task_id 丢失**。复现脚本输出：CAP1 task_id='task-A' / CAP2 task_id=''。

**修复**（语义保持，一次性凭证不变）：
- `codewiki/src/store.py` 新增 `archive_binding()` / `read_archived_binding()`：凭证消费后从 `task_bindings/<sid>.json` **退役到** `task_bindings/consumed/<sid>.json`（凭证失效，但保留 task_id 作归属墓碑）
- `capture_raw` 消费动作 `remove_binding` → `archive_binding`；新增兜底：supersede 未命中时回退读退役凭证，`task_source=binding-archived`
- `gc_bindings` 一并清扫 consumed/（按 bound_at 30 天），不无限堆积
- `config.py` 新增 `CONSUMED_BINDINGS_DIR`（gitignore 已按目录覆盖 `.meta/task_bindings/`）
- 回归测试 `tests/test_knowledge_store.py::test_attribution_survives_distilled_raw_via_archived_binding`
- 同步更正 `prompts.py` 里「绑定落盘即删除」的表述为「退役到 consumed/」

**验证**：复现脚本修复后 CAP2 = task-A / binding-archived；全量 pytest **933 passed, 2 skipped**。

**未修（且修不了）**：子代理侧 `mcp_get_tool_description` 报 `Server 'codewiki' not found or not connected` —— 该错误串全仓只出现在两处对话记录里，**不是本仓库代码**，是 IDE MCP 客户端的提示；子代理 `mcp_call_tool` 直调可用。

**关联决策冲突（未静默覆盖）**：`repowiki/notes/2026-08-24-task-bindings-绑定文件改为一次性消费凭证...md` 定的是「落盘后删除 + supersede 继承」。本次是把补偿机制补全（删除→退役），未推翻凭证语义；若要正式改结论需走 reject 旧笔记 + 新 decision。

### 2026-09-11 16:16

CLI 能力方案已归档为 docs/plans/cli-capability-progressive-disclosure.md（Status: deferred）：已 settle D1-D4、未 settle O1-O6，恢复判定线写死——/context all 实测 MCP 常驻 token 若只有几百~1k 则整个方案收手，若 22k+ 则 P1（Top 8 描述瘦身）照做；实测前不要再拿估算推进设计。

### 2026-09-11 16:16

AGENTS.md 精简两刀已落地：QwenWork 块删除（10,175→8,952）+ _TASK_MEMORY_AGENTS_SECTION 3,286→836（AGENTS.md 至 6,473，-36.4%），全量回归 924 passed；第三刀（Wiki 块 3,499 与 MCP 工具描述去重）必须等 P1 定下「信息归谁」后再做，顺序反了会丢信息。

### 2026-09-11 16:16

绑定凭证退役机制已落地：store.py 新增 archive_binding/read_archived_binding + binding-archived 回退，修复「绑定已消费+旧 raw 已被蒸馏 → 同会话再捕获归属丢失」漏洞（全量 933 passed，ADR-0006）；2026-08-24 旧决策笔记已 reject，新 decision/pitfall 两条已 stable。

### 2026-09-11 16:16

distill-worker 子代理 MCP 授权已修复（.codebuddy/agents/distill-worker.md 的 tools:ReadFile+toolsMCP 改为 mcpServers: codewiki），spawn 测试 2 tool uses 通过；子代理侧 mcp_get_tool_description 报 Server not found 但 mcp_call_tool 直调是通的（IDE 客户端问题，未修）。

### 2026-09-11 16:16

历史清理完成：filter-repo 清 PyPI token（uvx git-filter-repo --replace-text）+ 82MB gif（--invert-paths），两次 force-with-lease 推送，远端 develop = 068ad3f 与本地一致；d:/repos 6 个副本 .git/config 里同一枚 classic PAT 已全部摘除，待用户去 GitHub 撤销该 PAT 并清 Windows 凭据管理器缓存。

### 2026-09-11 16:16

遗留待办：两条疑似重复的 stable 笔记（2026-09-11-distill-conversation-submit-的-distilled-必须是-conversation-idn 与其 -fc7c66 副本）待读后 reject 一条；telemetry 只有 wiki 检索命中数据（hit/by_file/adopted），无 MCP 工具调用频次，按频次选 core 面暂无数据支撑。
