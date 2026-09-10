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
