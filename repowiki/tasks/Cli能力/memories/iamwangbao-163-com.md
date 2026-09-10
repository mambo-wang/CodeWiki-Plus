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
