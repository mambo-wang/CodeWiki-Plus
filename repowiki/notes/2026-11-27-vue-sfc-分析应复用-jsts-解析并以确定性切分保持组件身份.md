---
type: decision
title: "Vue SFC 分析应复用 JS/TS 解析并以确定性切分保持组件身份"
tags: ["codewiki", "decision", "javascript", "pascalcasename", "typescript"]
aliases: ["Vue SFC", "vue analyzer", "组件身份", "模板边", "script setup"]
metadata:
  date: 2026-11-27
  confidence_level: weak
  related_modules: ["dependency_analyzer", "mcp"]
  related_components: ["src/components/ArticleList.vue::ArticleList", "src/views/Home.vue::Home"]
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T01:31:25Z }
stale_after: 2027-11-27
---

## 背景

CodeWiki-Plus 需要分析 Vue 单文件组件，但本地已有 JavaScript/TypeScript analyzer、MCP 组件 ID 与增量缓存契约，不能整包覆盖 dependency_analyzer，也不应依赖首次运行下载 Vue grammar。

## 核心内容

用确定性扫描器只识别顶层 template/script/style，脚本外等长掩码并保留换行，再复用现有 JS/TS analyzer。组件保持 path::PascalCaseName 身份，Options API 成员与模板组件边单独提取；脚本与组件同名时改用 path::script.Name 并重映射关系。Vue caller 只对完整 path::symbol 放行精确跨语言命中，裸名仍按语言隔离。所有接入点与指纹缓存同步扩展。

## 原因

确定性切分能保持原文件行号、离线可用并避免把模板字符串误判为 SFC 标签；复用既有脚本解析可减少语义分叉。唯一组件身份与保守跨语言匹配可防止节点覆盖和错误依赖边。

## 边界

不执行模板或组件，不跟随 mixins、extends、全局注册和其他 bundler alias；不承诺完整 Vue 运行时或类型推导。grammar 缺失必须显式失败，大文件指纹使用全文流式哈希。
