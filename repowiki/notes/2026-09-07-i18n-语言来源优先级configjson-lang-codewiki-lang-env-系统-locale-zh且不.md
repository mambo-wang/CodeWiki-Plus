---
type: decision
title: "i18n 语言来源优先级：config.json lang > CODEWIKI_LANG env > 系统 locale > zh，且不能放项目级配置"
tags: ["decision"]
metadata:
  date: 2026-09-07
  task_id: 产品维护
  related_modules: ["mcp", "i18n", "config"]
  severity: medium
  source_ref: "conversations/conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md"
  scene: "MCP 国际化"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.7.0, at: 2026-09-07T06:51:05Z }
stale_after: 2027-09-07
origin: conversation

---

## 背景

用户最初的需求是「根据当前系统语言或者配置文件里配置的语言返回对应的语言」，需要确定语言从哪读、谁优先。

## 定案

优先级：**`~/.codewiki/config.json` 的 `lang` 字段 > 环境变量 `CODEWIKI_LANG` > 系统 locale 推断（`zh_*`→zh，其他→en）> 兜底 `zh`**。非法值记日志后回 zh。

注意区分两件事：「配置非法时的默认值回退」与「翻译缺失时的回退」是不同决策——后者本次定案为**不回退**（返回哨兵，靠发版前测试暴露）。

## 关键约束

语言源**不能放项目级 `repowiki/schema.yaml`**：MCP server 是无 repo 上下文的进程（`repo_path` 只是工具级参数），`prompts/list` 不接收 `repo_path`，启动期拿不到项目配置。用户级配置（`~/.codewiki/config.json`，见 `codewiki/cli/config_manager.py:29`）或环境变量才是 server 启动期可读的。项目既有惯例是 `CODEWIKI_*` 前缀环境变量（`CODEWIKI_HOME`/`CODEWIKI_USER`/`CODEWIKI_SERVER_LOG` 等，风格统一为 `os.environ.get(...) or 默认值`）。
