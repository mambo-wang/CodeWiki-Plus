---
type: pitfall
title: GitHub Release 正文乱码不可逆：UTF-8 字节被按 GBK 解码写入，只能基于事实重写
tags:
- github
- pitfall
metadata:
  date: 2026-09-05
  severity: medium
  source_ref: conversations/conv-发布新的pypi版本，并发布git-release.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.6.0
  at: 2026-09-05 11:30:42+00:00
stale_after: '2027-03-04'
origin: conversation
verified:
- by: codewiki/5.6.0
  at: '2026-09-05T12:47:35Z'
---

## Background

2026-09-04 创建 v5.6.0 GitHub Release 后，正文出现乱码，用户反馈"release 说明是乱码"。

## 现象与结论

- 乱码成因：UTF-8 字节被按 GBK 解码后写入（创建/上传时编码处理错误）。
- **直接还原不可行**：乱码字符串中已有字符在 GBK 解码时永久丢失（约每两个字丢一个），反向转换只能还原可读片段。
- 正确做法：基于真实变更事实（`git log v5.5.1..v5.6.0` 提交记录 + 相关文件核对）重写正文，并标注哪些措辞是语义推补、请用户重点核对。

## 预防

通过 REST API/脚本创建 Release 时，请求体必须显式按 UTF-8 编码发送，并避免任何 GBK 中间解码环节。

## Root cause

写入时字符编码不一致（UTF-8→GBK），且该转换有损不可逆。
