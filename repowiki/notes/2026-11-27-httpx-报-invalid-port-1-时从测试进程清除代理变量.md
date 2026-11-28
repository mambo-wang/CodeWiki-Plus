---
type: workaround
title: "httpx 报 Invalid port ':1]' 时从测试进程清除代理变量"
tags: ["codewiki", "workaround"]
metadata:
  date: 2026-11-27
  confidence_level: weak
  task_id: 他山之石
  source_session: "a9fe500b-4fa2-867d-99b1-62f00d609e09"
  related_modules: ["tests"]
  severity: medium
  source_ref: "conversations/conv-看看codewiki上游https-github.com-FSoft-AI4Code-CodeWiki-自从上次合并后有.md"
  scene: "本机全量测试运行"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T10:42:56Z }
stale_after: 2027-01-11
origin: conversation

---

## Background

本机全量 pytest 曾因宿主环境中的 NO_PROXY=[::1] 触发 httpx 错误 Invalid port: ':1]'，测试尚未进入有效断言就失败。

## 正确做法

仅在启动测试的子进程中移除 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY、NO_PROXY 及对应小写变量，再运行 `uv run python -m pytest -q`。可用 Python 的 env 字典过滤后 subprocess 启动，或 env -u 逐项清除；不要改产品代码来迎合本机代理格式。

## Rationale

该错误来自代理环境解析而非 CodeWiki 业务逻辑；隔离测试子进程能恢复可重复的本地验证，同时避免污染用户 shell 和全局网络配置。

## Root cause

httpx 将 NO_PROXY 中方括号包裹的 IPv6 loopback 条目按代理端口语法解析， malformed 值产生 ':1]' 端口错误。

## 恢复条件

当宿主或终端配置中的 NO_PROXY 已移除该 malformed 条目并重新启动进程后，可恢复普通测试命令；此 workaround 只适用于出现相同解析错误的本机测试场景。
