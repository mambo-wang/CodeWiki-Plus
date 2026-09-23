---
type: Conversation
title: "conversation 20260920T141437Z"
status: distilled
stale_after: 2026-12-19
generated: { by: codewiki/5.11.0, at: 2026-09-20T14:14:37Z }
captured_at: "2026-09-20T14:14:37Z"
content_hash: "sha256:7d901e8caf1b478f7f211783be4ae6c2fb41ddfc8c00fffd73b399082ae03aa2"
friction_score: 0
friction_signals: "correction=0,interrupt=0,repeat=0,user_turns=2"
keep_raw: false
link_to: ""
source_session: "58f3db625f10427ca1b8d507c25a7aed"
turn_count: 13
---

# Conversation Transcript

user: <working_memory_content>
The following is the existing working memory for this project. Use it as context.

# 长期记忆 (MEMORY.md)



## 环境偏好 / 约定



### npm 镜像源

- 当前环境（推测国内网络）使用 npm 官方源 `registry.npmjs.org` 下载**大体积原生二进制**（如 `@next/swc-darwin-x64`、better-sqlite3 预编译包）时速度极慢（<1KB/s，曾卡死 25+ 分钟）。

- 改用 `https://registry.npmmirror.com` 镜像源后速度约快 6 倍，全局安装 `npm install -g <pkg> --registry=https://registry.npmmirror.com` 是稳妥做法。

- 注意：npm 11 已不再识别 `--disturl` / `--prebuild-install-binary-host-mirror` 这类 CLI flag（会报 unknown config 警告），原生模块的二进制镜像需改用 `.npmrc` 配置。



## 已安装工具

- `omniroute`（AI 网关，v3.8.48，全局 npm 安装）：Dashboard `http://localhost:20128`，API `http://localhost:20128/v1`。编码工具 Base URL 指向 `/v1`、Model 用 `auto` 即可走免费后端。要求 Node ≥ 22.22.2（本机 v25.8.1 满足）。
</working_memory_content>

https://github.com/tamaratran/fast-jev-compaction 这个项目是做什么的，工作原理是什么，帮我安装一下
assistant: [tool: ask_followup_question · {"questions": "[{\"header\": \"任务关联\", \"multiSelect\": false, \"options\": [{\"description\": \"task_id=产品维护\"}, {\"description…
user: <question>本次会话要关联哪个任务？（若列表里没有想要的，可直接在输入框输入新任务名后回车）</question>
<answers>
本次不做任务关联，直接开始干活
</answers>
</question_item>
</questions>
</question_answer>
assistant: [tool: execute_command · git clone --depth 1 https://github.com/tamaratran/fast-jev-compaction.git "%TEMP%\fast-jev-compaction" 2>&1; ls "$env:TEMP\fast-jev-co…
assistant: [tool: execute_command · git clone --depth 1 https://github.com/tamaratran/fast-jev-compaction.git "$env:TEMP\fast-jev-compaction"]
assistant: [tool: list_dir · {"target_directory": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\fast-jev-compaction"}]
assistant: [tool: read_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\fast-jev-compaction\\README.md"}]

[tool: read_file · {"filePath": "C:\\Users\\Administrator\\AppData\\Local\\Temp\\fast-jev-compaction\\package.json"}]
assistant: 项目已了解。现在检查本机是否有 Claude Code CLI，决定安装方式：

[tool: execute_command · claude --version 2>&1; echo "---"; npm --version]
assistant: 本机没有 Claude Code CLI，无法按插件方式安装。先把它作为 npm 库全局安装（按记忆用国内镜像）：

[tool: execute_command · npm install -g fast-jev-compaction --registry=https://registry.npmmirror.com]
assistant: npm 上没有发布这个包（404），改为从源码构建安装：

[tool: execute_command · cd "$env:TEMP\fast-jev-compaction"; npm install --registry=https://registry.npmmirror.com 2>&1 | Select-Object -Last 5]
assistant: [tool: execute_command · cd "$env:TEMP\fast-jev-compaction"; npm run build 2>&1 | Select-Object -Last 10; npm test 2>&1 | Select-Object -Last 15]
assistant: 构建和测试全部通过。写入工作记忆后总结：

[tool: read_file · {"filePath": "d:\\repos\\CodeWiki-Plus\\.codebuddy\\memory\\2026-09-20.md", "limit": 20}]
assistant: ## 项目是做什么的

**fast-jev-compaction** 是一个 Claude Code 插件 + npm 库，用 TypeSafe 的 Jev 模型做**无损上下文压缩**，替代 Claude Code 内置的「摘要式」compaction。

核心思路：传统压缩让 LLM 把旧对话总结成一段摘要，但摘要有损——文件路径、精确报错、约束条件可能丢失。这个项目**从不改写任何内容**，只做「删除决策」：让 Jev 判断哪些 tool 调用/结果已过时，删掉或截断它们，用户和助手的文本原样保留。

## 工作原理（README + 源码核对）

1. **配对**：每个 `tool_use` 通过 `tool_use_id` 与其 `tool_result` 配对；首条消息和最近 N 条（默认 6）固定不动。
2. **构造状态**：发给 Jev 的是完整对话（旧→新），tool result 替换为短标记（`ok, 4213 chars (omitted)`），不摘要。
3. **分阶段压缩状态**到 25k token 上限内：tool 输入截断 1000→200→60 字符 → 长文本头尾截取 → 旧消息折叠为一行等，逐级应用直到装得下。
4. **打分**：对每个非固定调用问 Jev 两个问题——「调用本身是否还需保留」「结果是否需逐字保留」，返回保留概率。
5. **决策**（阈值 0.5）：`keepResult ≥ 阈值` → 全保留；否则 `keepCall ≥ 阈值` → 保留调用、结果截断为前 300 字符；否则连调用带结果一起删。
6. **重建消息列表**：失去全部内容的消息被移除，不会出现有结果没调用的悬空。

失败（Jev 报错、key 缺失、装不下）会抛异常，由调用方回退到内置摘要。

## 安装结果

- npm registry 上**没有发布这个包**（404），无法 `npm install fast-jev-compaction`。
- 已改为源码安装：克隆到 `C:\Users\Administrator\AppData\Local\Temp\fast-jev-compaction`，依赖安装（走 npmmirror 镜像）、`npm run build` 构建成功，**29/29 测试全部通过**。
- **注意**：本机没有安装 Claude Code CLI，所以插件方式（`claude plugin install fast-jev-compaction@fast-jev-compaction`）暂时不可用。若要作为 Claude Code 插件使用，需先安装 Claude Code（2.1.274+）并设置 `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` 和 `TYPESAFE_API_KEY`。
- 作为 npm 库使用：`import { compactMessages } from 'fast-jev-compaction'`（指向临时目录下的 `dist/`），运行需设置 `TYPESAFE_API_KEY` 环境变量。

如果你希望把它装进某个具体项目（比如 CodeWiki-Plus）作为依赖使用，或者需要先装 Claude Code CLI，告诉我即可。
