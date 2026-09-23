# 为什么 Open Code Review 找 Bug 这么准？——委托模式 Skill 使用与源码深度解析

> 写作时间：2026-09-21 · OCR 版本 v1.12.7 · 源码核对基于 [alibaba/open-code-review](https://github.com/alibaba/open-code-review) main 分支

**TL;DR:** Open Code Review（OCR）是阿里开源的 AI 代码审查 CLI。它的委托模式（Delegation Mode）把审查拆成两半：OCR 用纯确定性代码完成「该审哪些文件、按什么清单审」，宿主 AI Agent（Claude Code、Codex、Cursor 等）用自己的 LLM 完成实际推理——OCR 端零 LLM 配置。而它完整模式（`ocr review`）找 Bug 准确率高的根源，是一套「确定性工程 × Agent」的混合架构：纯函数文件筛选、52 份按语言定制的规则清单、语义分组分治、Plan→审查→行号校准→事实核查四阶段流水线，以及刻意「重精确、轻召回」的不对称设计。

---

## 一、这个 Skill 解决什么问题

如果你用过 Claude Code 这类订阅制 AI 编码代理做代码审查，大概率遇到过三个痛点（OCR README 原话）：

- **覆盖不全**——变更集一大，Agent 就开始「偷工减料」，只挑部分文件审；
- **位置漂移**——报告的问题对不上实际代码位置，行号或文件引用偏移；
- **质量不稳**——自然语言驱动的 Skill 难以调试，prompt 稍有变化审查质量就大幅波动。

根因是：**纯语言驱动的架构，对审查过程缺乏硬约束。**

委托模式 Skill 的解法是把「不能出错的环节」从语言模型手里拿走，交给确定性代码：

| 环节 | 谁负责 | 为什么 |
|------|--------|--------|
| 文件筛选（哪些该审、哪些排除） | OCR（Go 代码） | 漏文件是硬错误，不能靠概率 |
| 规则解析（按什么清单审） | OCR（Go 代码） | 模板匹配比自然语言引导更稳定 |
| Diff 获取 | 宿主 Agent（直接 git） | 简单直接 |
| 实际审查推理 | 宿主 Agent（自身 LLM） | 动态决策是 LLM 的强项 |

对订阅制用户来说还有个实际好处：**复用宿主 Agent 的订阅额度，不需要额外配置任何 API Key 或模型端点。**

## 二、Skill 的使用：七步工作流

安装两部分：

```bash
# 1. OCR CLI（前置条件，v1.9.0+ 才支持 --format）
npm install -g @alibaba-group/open-code-review

# 2. Skill 文件（复制 skills/open-code-review-delegate/SKILL.md 到你的 skills 目录）
```

装好后对宿主 Agent 说「用委托模式审查代码」，它会按 SKILL.md 的七步协议执行：

### 第 1 步：Preview——确定审查范围

```bash
ocr delegate preview --format json [--from main --to feature] [-c <hash>] [--exclude <patterns>]
```

输出 JSON 包含：mode（workspace/range/commit）、ref 元数据（from/to/commit/merge_base，供你拼 git 命令）、可审查文件列表（路径、状态、增删行数）、被排除文件及**排除原因**。

三种常见场景：

| 场景 | 命令 |
|------|------|
| 工作区变更（含未跟踪文件） | `ocr delegate preview` |
| 分支对比 | `ocr delegate preview --from main --to feature` |
| 单次提交 | `ocr delegate preview -c abc123` |

### 第 2 步：获取文件规则

```bash
ocr delegate rule --format json <path1> <path2> ...
```

传入第 1 步的可审查文件路径，输出**按规则内容分组**的结果——共享相同规则的文件归为一组，避免重复。

### 第 3 步：获取 Diff

按 mode 用 git 直接取：range 模式 `git diff <merge_base>..<to> -- <path>`；commit 模式 `git show <commit> -- <path>`；workspace 模式已跟踪文件 `git diff HEAD -- <path>`，**未跟踪文件直接读全文**（整个文件都是新代码）。

### 第 4 步：逐文件审查

为每个 `reviewable_files` 条目建 checklist（以 `(path, status)` 为身份——workspace 模式下「staged 删除 + untracked 重建」会让同一路径出现两次）。每个文件：取 diff → 对照规则组清单 → 深入审查 → 标记 `reviewed` 或带具体原因的 `skipped`。大变更按共享规则分批，**不要找到第一个高危问题就停**。

### 第 5-6 步：结构化输出与覆盖率报告

每条评论必须含 `path`、`content`，可选 `start_line`/`end_line`、`category`（bug/security/performance/...）、`severity`（critical/high/medium/low）。报告前必须核对每个文件都有去向，输出 `total_files`、`reviewed_files`、`skipped_files`、`coverage_rate`——**覆盖率是强制的，不许静默漏文件**。

### 第 7 步（可选）：修复

用户要求 "review and fix" 时：Critical/High 直接修，Medium 描述修法，Low 除非顺手否则跳过。

## 三、源码实现原理：npm 包背后是一个 Go 二进制

`npm install -g @alibaba-group/open-code-review` 装的其实是个**二进制分发器**——仓库 `npm/` 下按平台预编译（darwin-arm64/x64、linux-arm64/x64、win32-arm64/x64），npm 包根据平台下载对应的 Go 编译产物。核心代码全在 Go 里：

```
cmd/opencodereview/     # CLI 入口（cobra）
internal/agent/         # 审查流水线：筛选、分组、调度
internal/llmloop/       # 工具调用循环、评论工作池、内存压缩
internal/tool/          # 6 个内置工具
internal/config/rules/  # 规则引擎：system_rules.json + 52 份 rule_docs/*.md
internal/config/template/ # 12 份 prompt 模板（plan/main/re_location/review_filter/...）
internal/delegate/      # 委托模式：规则分组
```

### 委托模式的实现出奇地薄

`cmd/opencodereview/delegate_cmd.go` 里，`preview` 子命令直接复用完整模式的 `agent.Preview()`，但**故意不传 Template**（delegate_cmd.go:119-133 的注释写明：宿主 Agent 用自己的上下文窗口审查，OCR 的 max_tokens 不是委托工作的限制）。`rule` 子命令则调用 `internal/delegate/rulegroup.go` 的 `GroupRules`：以 `source + "\x00" + pattern + "\x00" + text` 为 key 聚类（rulegroup.go:46），来源、匹配模式、规则文本三者完全一致才归同组——两份规则文本相同但来源不同的文件保持分组独立，保证每组的元数据对组内所有文件都准确。

这就是委托模式的全部：**两个只读命令，输出一份「审查规格」，零 LLM 调用。**

## 四、为什么它找 Bug 这么准——六个设计决策

现在回答核心问题。注意区分：委托模式下这些机制里只有 ①② 交给宿主 Agent 复用，③④⑤⑥ 是完整模式 `ocr review` 的流水线——但它们共同解释了 OCR 的准确率从哪来。

### ① 文件筛选是纯函数，preview 和真实运行共用同一答案

`internal/agent/selection.go:43` 的 `selectFiles` 是纯函数——无输出、无副作用、不碰 git 和 LLM。每个变更文件过一遍静态门：二进制 → 凭据路径（`IsSecretPath`，优先级高于一切用户规则）→ 用户排除 → 扩展名白名单 → 默认路径排除（vendor/node_modules 等）→ 删除文件 → 单文件 diff token 上限。注释里点明设计动机：`--preview` 和真实运行消费同一个答案，而不是各自推导——「这正是两者曾经漂移的原因」（#782）。

**准确率的第一个来源：不漏文件。** 通用 Agent 审查大变更集时「选择性偷懒」，在这里被工程逻辑堵死了。

### ② 52 份按语言定制的规则清单，每条都带「不要报告」排除项

`internal/config/rules/system_rules.json` 用有序的 glob→规则映射覆盖 50+ 种语言（`**/*.go → go.md`、`**/*.{ts,js,tsx,jsx,mjs,cjs} → ts_js_tsx_jsx.md`……），首个匹配生效，未命中回退 `default.md`。规则正文是嵌入二进制的 Markdown（`//go:embed system_rules.json rule_docs/*`）。

以 `rule_docs/python.md` 为例，第一行就是定调宣言：

> Favor precision over recall: only raise an issue when you are confident it is a real defect... a false alarm costs more reviewer trust than a missed minor issue.

之后每个类别——可变默认参数、边界处理、异常处理、资源管理、并发、安全——都是「该报什么 + **不该报什么**」成对出现。比如 `.pyi` 存根文件的未用导入不算死代码；性能问题先确认热路径和数据规模再报；并发问题必须有并发调用证据。甚至有个内容嗅探器（`sniffer.go:32-44`）：`.m` 扩展名 MATLAB 和 Objective-C 都用，读文件首个非空行判断语言——而且嗅探器刻意包在系统层而非最外层，避免覆盖用户自定义的 `.m` 规则。

**准确率的第二个来源：把「误报成本高于漏报」写进每份清单，并用排除项封住 LLM 最常见的过度报告路径。**

### ③ 语义分组 + 分治，上下文隔离

`internal/agent/grouping.go`：变更文件先由一次轻量 LLM 调用按语义分组（如 `message_en.properties` 和 `message_zh.properties` 捆在一起审），每组上限 10 个文件（`maxFilesPerGroup = 10`），再按 token 预算约束。每组作为独立子任务、隔离上下文、并发审查（默认并发 8）。小变更集直接本地打包不浪费 LLM 调用；分组失败降级为逐文件。

**第三个来源：大变更集不丢上下文质量——每组都是干净的小上下文，而不是塞爆的巨型 prompt。**

### ④ 四阶段 LLM 流水线，每阶段只干一件事

完整模式的 `Agent.Run`（agent.go:278 起）：解析 diff → 分组 → 每组先跑 **PLAN_TASK**（plan_task_system.md：识别风险点、按严重度排序、规划工具调用策略，但「工具仅供规划参考，不得实际调用」）→ 进入 **MAIN_TASK** 工具循环 → 评论后处理。

MAIN_TASK 的 system prompt（main_task_system.md:16-19）有严格的聚焦规则：逐文件审查、鼓励跨文件发现不一致、**上下文工具只用于收集背景，评论必须指向 `<review_files>` 内的代码**。结束前必须确认每个文件都有独立的一轮——「审了实现文件不等于审了它的头文件」。

评论产出走结构化工具 `code_comment`（code_comment.go），category/severity 是枚举校验的，不是自由文本。甚至有个细节：`report_incorrect_comments` 工具的 JSON 字段顺序是刻意设计的——`analysis` 在 `comment_ids` 之前，让模型先推理再承诺；顺序反了它就会先选 id 后找理由（agent.go:1567-1574 的注释记录了这个来自真实会话回放的教训）。

### ⑤ 行号校准 + 事实核查，两个独立的质量模块

LLM 报问题最常见的失败是**位置漂移**和**事实错误**。OCR 用两个独立 LLM 任务分别治理：

- **RE_LOCATION_TASK**（re_location_task_system.md 全文就一句话）：给定 diff 和评论，提取评论所指的精确代码片段——把评论锚定回真实行号。
- **REVIEW_FILTER_TASK**（review_filter_task_system.md）是个「事实核查员」，只删 diff 能**证明**是事实错误的评论。它的 prompt 把不对称错误成本写得非常清楚：

> Keeping an incorrect comment costs a reviewer a few seconds of attention. Removing a correct comment silently destroys a real finding... So when your evidence falls short of proof, approve.

「可疑」「我无法验证」「价值不高」统统等于放行。核查员只能看到 diff，看不到审查 Agent 读过的完整代码——所以它天然只能否决「diff 直接反驳」的评论，不能凭直觉杀评论。

**第四、五个来源：位置和事实这两个 LLM 最易失真的维度，各有一个专职模块兜底，且删除门槛刻意设得极高。**

### ⑥ 克制的工具集 + 三区内存压缩

内置工具只有 6 个（definitions.go:17-25）：`task_done`、`code_comment`、`file_read`、`file_find`、`file_read_diff`、`code_search`。README 说这是从大规模生产数据的工具调用 trace 里蒸馏出来的——按调用频率分布、单工具重复率、新工具对调用链的影响筛选。对比通用 Agent 的几十个工具，小工具集让模型行为更稳定可预测。

长对话用三区内存压缩（compression.go:20-23）：token 用量到 60% 触发后台异步压缩，到 80% 立即同步压缩。压缩摘要按五个结构化维度输出（已确认问题、工具调用结论、已完成/待办、当前焦点），保证压缩后审查不重启、不遗忘已确认的发现。

## 五、代价与权衡

诚实地说，这套设计不是免费的：

- **召回率刻意低于通用 Agent。** README 的 benchmark（50 个热门开源仓库、200 个真实 PR、10 种语言、80+ 高级工程师标注的 1505 个 ground-truth 问题）显示：同等模型下 OCR 的 Precision 和 F1 显著更高，token 消耗约 1/9，速度更快——但 **Recall 更低，这是刻意用召回换精确**。宁可少报，不可误报。
- **委托模式拿不到完整流水线。** Plan、行号校准、事实核查这些 LLM 阶段在委托模式下不存在——宿主 Agent 自己承担这些质量责任。OCR 只交付文件清单和规则清单这两块确定性脚手架。换句话说：委托模式的审查质量上限取决于宿主 Agent 的自律程度，SKILL.md 里的「覆盖率强制」「不要找到第一个高危就停」等约束就是在补偿这个差距。
- **规则是静态的。** 52 份清单再精细也是通用清单，项目特有约定要靠 `--rule` 自定义 rule.json 补充。

## 六、上手建议

```bash
# 安装
npm install -g @alibaba-group/open-code-review
ocr --version   # 确认 ≥ 1.9.0（--format 标志的最低版本）

# 委托模式两步试用（无需任何 LLM 配置）
ocr delegate preview --format json
ocr delegate rule --format json src/main.go

# 有需求上下文时带上 background（会出现在 preview 输出里供审查参考）
ocr delegate preview -B requirement.md
```

如果你是订阅制 Agent 用户、只想复用额度：委托模式。如果你要 CI/CD 里的无人值守审查：完整模式（`ocr review --format json --output result.json`）。

## Further Reading

- [alibaba/open-code-review](https://github.com/alibaba/open-code-review) — 源码与文档站
- [委托模式文档](https://open-codereview.ai/docs/delegate) / [Agent Skill 文档](https://open-codereview.ai/docs/agent-skill)
- AACR-Bench 数据集（HuggingFace: Alibaba-Aone/aacr-bench）— benchmark 的 1505 个标注问题
- 本仓库 `.codebuddy/skills/open-code-review-delegate/SKILL.md` — 已安装的 Skill 原文
