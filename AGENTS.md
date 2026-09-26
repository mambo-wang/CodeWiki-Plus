<!-- CodeWiki LLM Wiki -->

## CodeWiki LLM Wiki

本项目已使用 [CodeWiki](https://github.com/mambo-wang/CodeWiki-Plus) 生成 LLM Wiki 文档，位于 `repowiki/` 目录。

**入口文件：**

- [`repowiki/wiki/overview.md`](repowiki/wiki/overview.md) — 仓库级架构总览（含 Mermaid 架构图）
- [`repowiki/wiki/index.md`](repowiki/wiki/index.md) — 文档目录与知识笔记索引
- [`repowiki/schema.yaml`](repowiki/schema.yaml) — 项目文档约定（命名规范、必填章节等）

### 使用建议

1. **编码前**：`query_wiki` 搜模块文档，了解架构约定和依赖关系
2. **做决策时**：`query_wiki` 搜已有 `decision` 笔记，避免重复讨论
3. **完成重要决策后**：`ingest_note` 归档；**被用户纠正/吐槽时**：反思→起草→征求确认后归档（三步流程与归档示例见 `get_prompt(name="ingest-note")`）
4. **定期维护**：`lint_wiki` 检查文档是否过时

### 回答时显式标注依据

- 引用 `query_wiki` 检索结果 → 标注 `（依据：<file>）`，与返回的 `file` 字段完全一致；
- 引用代码事实 → 标注 `<代码文件>:<行号>`，行号以实际读取为准；
- 依据来自本次代码核对 → 明说来源。

### 采纳声明（检索反馈）

通过 `query_wiki` 检索并**实际使用了**某条结果时，在最终回复末尾附带：

```
<!-- codewiki:referenced-docs: ["notes/pitfall-xxx.md", "wiki/modules/yyy.md"] -->
```

路径与 query_wiki 返回的 `file` 字段完全一致。声明过的文档获得采纳计数、检索排序提升；零采纳高频笔记会被 `lint_wiki` 的 `low_adoption` 检查标记。只声明真正用到的——漏报可容忍，误报不可容忍。

### 主动知识沉淀

触发信号（任一）：多步骤调试定位根因、多方案讨论后做出选择、代码行为与文档/命名不一致、用户补充隐性项目知识、调研收敛到明确结论、发现可复用模式。

**四问过滤（全部通过才记录）：** 下次对话还能用到？其他 Agent/新同事能直接受益？`query_wiki` 确认未覆盖？属于"事实/决策/模式/教训"而非临时状态？

**路由表：** 技术选型→`ingest_note(note_type="decision")`；踩坑→`pitfall`；经验教训→`lesson`；架构发现→`architecture`；临时绕过（含恢复条件）→`workaround`；多方案对比→`write_doc_file(page_type="comparison")`；调研存档→`write_doc_file(page_type="query")`。

执行细节（结构化模板、查重、确认流程）见 `get_prompt(name="ingest-note")`。不要记录：本次任务临时变量/路径/参数、个人偏好、代码注释或 README 已写明的信息、未经验证的猜测。

### 产出语言（语言闸门）

所有产出使用**中文**——Wiki 文档、笔记、代码注释、commit message、给用户的回复，除非用户明确要求其他语言。检索到的历史文档若为其他语言，新产出仍按本规则。

<!-- /CodeWiki LLM Wiki -->

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (uses the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

## Team memory fusion (conversation → Wiki)

对话经验蒸馏进知识飞轮的实现入口与设计约束（Mode A/B/C、raw 暂存区语义、distilled_file 侧通道），见 [`repowiki/wiki/team-memory-fusion.md`](repowiki/wiki/team-memory-fusion.md)。

<!-- TEAM-MEMORY-TASK:START -->
## Task memory (任务记忆)

跨会话延续长线工作上下文。任务记忆是**任务范围内的进度知识**，与 Wiki 笔记（**跨任务的通用经验**）互补。

**会话开始时（必须执行）**：若本会话已收到 SessionStart hook 注入的任务关联指引，按其执行（弹框规则、补蒸馏、收尾采集以注入为准）；**未收到注入时**，按 `get_prompt(name="task-workflow")` 的「会话开始：关联任务」一节执行——用 `ask_followup_question` 弹一次任务关联框（一框列全所有进行中任务 + 新建 + 跳过），绑定后 `get_task_context` 拉取上下文。

完整工作流（补蒸馏、会话中采集、收尾、检索、存储布局与实现约束）见 MCP prompt：`get_prompt(name="task-workflow")` —— 按需获取。
<!-- TEAM-MEMORY-TASK:END -->

<!-- CODEWIKI-ACTIVE-SETTLE:START -->
### 主动沉淀协议（自然停顿点即写即沉淀）

与批处理（收尾采集 → 下轮蒸馏）互补：停顿点即写即沉淀，任务记忆与草稿笔记下一轮 `get_task_context` 即可见，不必等蒸馏。

**① 自然停顿点判据（命中任一即沉淀；每轮回复收尾前自查，不要依赖「想起来」）：**
1. 任务里程碑达成；
2. 关键技术决策落定，或澄清/纠偏了产品机制、代码事实等关键认知；
3. 用户话题明显转向；
4. 收尾轮（强制兜底，必做）——无论会话中是否命中前三条，收尾轮必须做一次沉淀自查：本会话是否有未沉淀的进展/决策？有则按下方两条路径补写。

**不做字面每轮沉淀**：任务记忆追加无去重，每轮都写会灌爆记忆并反复触发 40 条/24KB 压缩阈值——只在停顿点沉淀。**宿主 IDE 自带的工作记忆（如 `.codebuddy/memory/`）与本协议的任务记忆是独立通道**，写了前者不豁免后者。

**两条写入路径（均当轮落盘，下一轮 `get_task_context` 即取；禁止手写文件）：**
- 任务记忆：`add_task_memory(task_id=<绑定的任务id>, content="本段进展/决策/下一步")` 直写——无需确认。写入标准：只记会改变下一步行动的进展/决策/约束；推翻旧记忆时传 `supersedes=<旧条目id>`，不要追加平行副本；近重复写入会被拒绝（difflib > 0.85），改用 supersedes 或合并改写后重试；
- 通用经验：`ingest_note(status="draft", ...)` 落草稿——**确认闸门保留**：草稿笔记须经 `confirm_note` 确认后才进入全局检索语料，不得跳过确认。草稿落盘即可被下一轮 `get_task_context` 的 `related_notes` 以 `status: draft` 展示、能确认、能参与冲突检测。
<!-- CODEWIKI-ACTIVE-SETTLE:END -->
