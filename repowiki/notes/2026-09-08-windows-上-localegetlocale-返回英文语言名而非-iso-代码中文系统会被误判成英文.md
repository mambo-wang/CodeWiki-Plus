---
type: pitfall
title: Windows 上 locale.getlocale() 返回英文语言名而非 ISO 代码，中文系统会被误判成英文
tags:
- pitfall
metadata:
  date: 2026-09-08
  related_modules:
  - mcp
  - i18n
  severity: medium
  source_ref: raw\conv-@d-repos-CodeWiki-CN-codewiki-mcp-prompts.py-代码里的prompt的titl.md
  scene: MCP 层 i18n
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-08 05:12:03+00:00
stale_after: '2027-03-07'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-08T05:28:17Z'
---

## Background

用户 MCP 配置里没设任何语言变量（`env` 未配 `CODEWIKI_LANG`），`prompts/list` 却返回英文。按定案的语言优先级（config.json `lang` > `CODEWIKI_LANG` env > 系统 locale > 兜底 zh），中文 Windows 应判为 zh——所以这是真 bug。

## Root cause

Python 在 Windows 上 `locale.getlocale()` 返回的是**语言名而不是 ISO 代码**：

```
locale.getlocale() -> ('Chinese (Simplified)_China', '936')   # 不是 'zh_CN'
```

而判断只写了 `code.startswith("zh")`，`"chinese (simplified)_china"` 不匹配，于是落到「非 zh → en」。繁体 `Chinese (Traditional)_Taiwan` 同样中招。

## 正确做法

判定中文时**同时**接受 ISO 代码前缀与语言名：`code.startswith("zh") or "chinese" in code.lower()`。已在 `codewiki/mcp/i18n.py` 修复，并新增 `tests/test_i18n.py::test_resolve_windows_locale_names` 钉住简体/繁体/英文三支。

## 附加事实

语言在 **server 进程启动时解析一次**，改配置后必须重启 MCP（IDE 里重载/禁用再启用，或重启 IDE）才生效。
