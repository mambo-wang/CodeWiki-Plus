---
type: pitfall
title: "repowiki/conversations/ 未被 .gitignore 忽略且含原始转录，提交前必须扫 secret"
tags: ["github", "pitfall"]
metadata:
  date: 2026-09-11
  related_modules: ["repowiki", "capture", "git"]
  severity: medium
  source_ref: "raw\\conv-@command-codewiki-蒸馏对话提取记忆和经验.md"
  scene: "蒸馏产物提交推送"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T01:06:04Z }
stale_after: 2027-03-10
---

## 背景

蒸馏完成后批量提交产物时做密钥扫描，在 `repowiki/conversations/conv-发布版本.md`、`conv-推送代码.md` 中发现**真实 PyPI token**（`pypi-AgEI...` 明文）。这两个文件早已推送到 origin，属历史遗留泄露。

## 事实

- `.gitignore` 只忽略了 `repowiki/raw/`（暂存区，标注「never commit it」），**`repowiki/conversations/` 未被忽略**（2026-09-11 核对）。而 conversations/ 放的是蒸馏后归档的原始对话转录——与 raw 同类，都可能原样留存命令输出里的 token。
- GitHub Push Protection **只扫本次新增的提交**：已入库的旧文件不会因新推送被拦，所以「推送成功」不等于「仓库无 secret」。

## 正确做法

提交推送蒸馏产物前：

1. 用 `search_content` 扫 `repowiki/`（conversations、notes、skills、tasks 全扫），不要依赖 PowerShell 正则——本仓中文路径 + 复杂正则在 PowerShell 里会解析失败；
2. 提交范围只收知识产物（`notes/`、`skills/`、`tasks/`、`wiki/log-*.md`），主动排除 `repowiki/conversations/` 与 `.codebuddy/skills/`（后者是生效区副本，与 `repowiki/skills/` 草稿区冗余）；
3. 已确认泄露的 token **必须到发行方轮换**（进过仓库即视为泄露），想从历史清除再跑 `git filter-repo`——会改写 develop 历史，需先与协作者同步。

## 根因

归档目录（conversations/）与暂存目录（raw/）存放同类内容，但只有后者进了 .gitignore，忽略规则没有随「蒸馏后归档」这个新写路径同步扩展。

## 关联

与 pitfall『GitHub Push Protection 拦截含 secret 的提交：追加删除提交无效，必须改写原提交』互补：那条讲被拦后怎么改，本条讲如何不让它进提交；同时与『Windows PowerShell 下 git add 中文路径会静默失败』同源——本仓 Windows 环境下 git 相关静默失败多发，提交后一律用 `git status -sb` / `git log -1 --stat` 复核实际入库内容。
