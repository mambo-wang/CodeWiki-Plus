---
type: pitfall
title: "验收 lint_wiki 结果先识别 file 侧通道再读 JSON"
tags: ["codewiki", "keyerror", "pitfall"]
metadata:
  date: 2026-11-26
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["MCP_Tools_Lint", "mcp"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的-770c00.md"
  scene: "Wiki lint 自动验收"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.7, at: 2026-11-25T23:02:51Z }
stale_after: 2027-05-25
origin: conversation

---

## Background

`handle_lint_wiki` 通过 `write_result(...)` 写报告时，返回值可能是文件侧通道，例如：

```json
{
  "file": "/Users/kirito/repos/CodeWiki-Plus/.codewiki/workspace/lint_report.json",
  "total_issues": 0
}
```

它不一定内联返回 `issues`。验收脚本若直接访问 `result["issues"]`，会得到 `KeyError`，即使 lint 本身已经成功。

## 正确做法

1. 先判断结果是否包含 `file`；有则读取该 JSON 文件，再按报告结构取 `issues`、计数等字段。
2. 没有 `file` 时再按内联结果处理。
3. 读报告后立即使用或备份；`lint_report.json` 会被后续 `lint_wiki` 调用覆盖，这与响应形状是两个独立问题。

## Rationale

MCP 工具为控制大结果体积会把完整报告落到工作区文件，只回传路径。把“结果一定内联”当成契约会让自动验收在工具成功时误报失败。
