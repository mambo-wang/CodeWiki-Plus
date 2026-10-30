---
type: pitfall
title: "PowerShell 下命令输出与临时文件的四个编码/语法坑：%TEMP% 不展开、utf8NoBOM 不支持、重定向是 UTF-16 LE、管道输出可能为空"
tags: ["pitfall", "powershell"]
metadata:
  date: 2026-10-30
  confidence_level: weak
  task_id: 发版本
  source_session: "5dee23d20a5649afa4429fdc1594bc07"
  severity: medium
  source_ref: "conversations/conv-@command-windows-python-release-发布版本5.16.3.md"
  scene: "发版本"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.5, at: 2026-10-30T03:28:47Z }
stale_after: 2027-04-28
origin: conversation

---

## 现象与正确做法（Windows PowerShell 发版/测试流程实测）

1. `%TEMP%` 是 cmd 语法，PowerShell 中不展开——`python -c "open(r'%TEMP%\\x.txt','w')..."` 会写向字面名为 `%TEMP%` 的路径，后续 git commit -F 静默不生效。PowerShell 中用 `$env:TEMP`。
2. 旧版 PowerShell 的 `Set-Content -Encoding utf8NoBOM` 报编码参数不兼容。写 commit message 等临时文件改用 Python：`python -X utf8 -c "open(path,'w',encoding='utf-8').write(...)"`。
3. PowerShell `>` 重定向产生的日志是 UTF-16 LE 编码，Python 按 utf-8 解码会得到乱码或空统计，须 `.decode('utf-16')`。
4. 长时命令（如全量 pytest 约 16 分钟）直接管道取尾部输出可能为空（缓冲问题），应重定向落盘日志文件后再读。

## Rationale

四个坑的共同特征是「命令看似执行了但结果拿不到/文件没写成」，在发版闸门等关键流程中属静默失败，排查成本高，值得固化为 Windows 环境标准做法。
