---
type: decision
title: PyPI 发布凭据不落仓库工作树：用 Windows 凭据管理器（keyring）存储 token，否决技能文件夹+gitignore 方案
tags:
- decision
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: f218ce7f76474a3e8b2cffab2df60584
  related_modules:
  - release
  - windows-python-release
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-8.md
  scene: 发布流程
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:42:28+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:58:08Z'
---

## 背景

发布小版本时用户提议：把 PyPI API token 放到技能文件夹的 config 文件里，并加入 gitignore。

## 否决

该方案机械上可行但不推荐：
1. `.codebuddy/` 是被 git 跟踪的目录（公开仓库），技能文件本身就在版本库里；gitignore 只对未跟踪文件生效——一旦 `git add -f`、ignore 条目丢失或换机器同步，token 直接进公开仓库。
2. 本仓库已有 4 次以上 token 泄露事故，全部源于「token 落在仓库工作树文件里」被对话采集 hook 或提交带走。
3. gitignore 只是防误提交的便利机制，不是安全边界。

## 落地

改用 Windows 凭据管理器（keyring）：
- 存储：`keyring.set_password('pypi', 'upload', '<token>')`——加密、在仓库之外、无需 gitignore。
- 读取：发布脚本直接 `keyring.get_password('pypi', 'upload')`，不再要求用户把 token 粘贴到对话。
- 技能更新：`windows-python-release`（源文件 + 生效区副本）步骤 7 的 token 来源改为 keyring；禁忌清单新增「不存仓库内文件」「不让用户粘贴 token 到对话」。

## 教训

粘贴 token 到对话本身就是泄露源（对话采集 hook 会原样归档）；发布后若 token 曾入会话记录，应到后台轮换并重新写入 keyring。
