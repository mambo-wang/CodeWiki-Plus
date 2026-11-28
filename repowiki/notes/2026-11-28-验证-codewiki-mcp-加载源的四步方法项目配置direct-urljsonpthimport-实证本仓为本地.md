---
type: lesson
title: "验证 CodeWiki MCP 加载源的四步方法：项目配置→direct_url.json→pth→import 实证；本仓为本地 editable，改码重启 MCP 即生效"
tags: ["codewiki", "lesson"]
metadata:
  date: 2026-11-28
  confidence_level: weak
  source_session: "81fc45f7-e7a0-4e83-9538-f6c14de91c4b"
  related_modules: ["mcp", "setup", "cli"]
  severity: medium
  source_ref: "conversations/conv-现在codewiki-mcp用的是本地codewiki-plus代码还是pypi依赖.md"
  scene: "MCP 加载源排查"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.8, at: 2026-11-27T21:57:09Z }
stale_after: 2027-05-27
origin: conversation

---

## Background

用户问「现在 codewiki mcp 用的是本地 codewiki-plus 代码还是 pypi 依赖」。本仓库（D:\repos\CodeWiki-Plus）实测结论：**本地 editable 安装，不是 PyPI 包**。

## 验证方法链（四步实证）

1. **项目 MCP 配置**：`.qoder/settings.json` 的 codewiki server command 指向仓库内 `.venv\Scripts\python.exe`、工作目录 `${workspaceRoot}`——先确认用的是哪个解释器；
2. **安装元数据**：读 `.venv/Lib/site-packages/codewiki_plus-<版本>.dist-info/direct_url.json`，`{"url":"file:///D:/repos/CodeWiki-Plus","dir_info":{"editable":true}}` 即 editable 本地安装；
3. **pth 指向**：`_editable_impl_codewiki_plus.pth` 内容指向仓库根；
4. **导入实证**：用该解释器跑 `python -c "import codewiki; print(codewiki.__file__)"`，输出 `D:\repos\CodeWiki-Plus\codewiki\...` 即本地代码。

注意区分：依赖包（uv.lock 锁定的第三方库）仍来自包索引，但 codewiki-plus 本体是本地 editable。

## 生效语义（与 hook 不同）

MCP server 是常驻进程：修改本地代码后**重启 MCP 会话才生效**（区别于 command 型 hook 每次从磁盘直执行、下次事件即生效）；无需从 PyPI 更新。

## Rationale

「改了代码为什么没生效」与「到底跑的哪份代码」是高频疑问；四步验证链可确定性回答，避免凭记忆猜测。editable 安装是本仓库开发模式的既定事实，后续排查 MCP 行为异常时应先确认加载源。
