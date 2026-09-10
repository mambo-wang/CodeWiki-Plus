---
type: pitfall
title: hatchling wheel artifacts 不含新增包内资源，新增 locales/*.yaml 需同步改 pyproject
tags:
- pitfall
metadata:
  date: 2026-09-07
  task_id: 产品维护
  related_modules:
  - mcp
  - i18n
  - 打包
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md
  scene: 打包发版
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: 2026-09-07 06:50:55+00:00
stale_after: '2027-03-09'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-10T07:47:21Z'
---

## 背景

i18n 方案引入 `codewiki/mcp/locales/*.yaml` 这类包内非 py 资源。查 `pyproject.toml:98-102`，hatchling wheel 的 `[tool.hatch.build.targets.wheel] artifacts` 只列了 `codewiki/templates/**/*`、`py.typed`、`codewiki/agents/**/*`。

## 坑

新增 `locales/*.yaml` **不会自动进 wheel**，必须同步写进 artifacts，否则本地开发读得到、装包后 `yaml.safe_load` 找不到文件直接失败。

## 正确做法

任何新增的包内非代码资源（yaml/json/tpl），都要同步检查打包配置；并把「装包后能读到资源」作为发版前检查项，而不是只验证源码树内运行。

## 与既有知识的区别

区别于「build 后端 setuptools→hatchling 迁移后 wheel 内容会变化」（那次是后端切换导致清单变化，靠构建后 `unzip -l` 对比发现）：本条是**在既有 hatchling 配置下新增资源类型**的增量场景，触发动作是「改 artifacts」，不是「对比新旧 wheel」。
