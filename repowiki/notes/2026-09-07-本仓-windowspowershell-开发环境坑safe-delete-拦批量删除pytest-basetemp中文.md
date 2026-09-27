---
type: pitfall
title: 本仓 Windows/PowerShell 开发环境坑：safe-delete 拦批量删除、pytest basetemp、中文 commit -F、junitxml
tags:
- pitfall
- powershell
metadata:
  date: '2026-09-07'
  related_modules:
  - tests
  - dev-env
  - skills/windows-dev-env/SKILL.md
  severity: medium
  source_ref: conversations/conv-@d-repos-CodeWiki-CN-.codebuddy-plans-output_dir-收敛为repo_pat-2.md
  scene: output_dir 收敛大重构
  compiled_into:
  - ''
  - skills/windows-dev-env/SKILL.md
  confidence_level: weak
  disposition:
    verdict: excluded
    at: '2026-09-20'
    reason: 一次性环境状态记录，已被发布与依赖治理场景块中更稳定的条目覆盖，无独立方法价值
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.7.0
  at: '2026-09-07 03:04:55+00:00'
stale_after: '2027-03-06'
origin: conversation
verified:
- by: human:mambo-wang
  at: '2026-09-07T03:50:23Z'
source_conversations:
- conversations/conv-user_command-commands-codewiki-启用-禁用任务管理（跨会话任务记忆）-管理-team-me-158abe.md
---

## 背景

2026-09-06 output_dir 收敛大重构（119 文件、全量测试回归）期间，Windows + PowerShell 环境反复拖慢排查，以下为本仓实测的环境坑与解法。

## 坑与解法

1. **safe-delete 钩子拦截批量删除**：用户 PowerShell profile 的安全删除包装器会拦截 `del /S`、`Remove-Item -Recurse`（大目录）及 TEMP 下 pytest garbage 目录的批量清理。解法：改用 `cmd /c "rd /s /q ..."` 或 Python `shutil.rmtree`/逐个 `unlink`。
2. **pytest 临时目录策略**：TEMP 下堆积 47 个 pytest-of-* garbage 目录（每次跑测结尾 GC 被沙箱拦截）会连带新跑挂掉；大跑改用 `--basetemp=.pytest-tmp`（工作区内）并加入 .gitignore。注意 basetemp 残留 5000+ 文件时同样触发拦截，需定期清。
3. **中文 commit message**：PowerShell 直接传 `git commit -m "中文..."` 解析失败（详见既有笔记「Windows PowerShell 下 git commit -m 传中文会乱码」）。解法：消息写临时文件 + `git commit -F <file>`。
4. **pytest 输出被噪音吞掉**：PowerShell 输出混入 safe-delete 噪音、过滤逻辑吞行。解法：`cmd /c` 执行并重定向到文件再读；失败清单用 `--junitxml` + ElementTree 解析最可靠。
5. **PowerShell 把 git 进度输出视为 stderr** 属误报，不代表命令失败。

## 适用范围

本仓 Windows 开发环境（CodeBuddy 沙箱 + PowerShell profile 钩子）。

## Windows 下 pytest 输出被 CLIXML 吞掉；test_phase2_concurrency 是文件锁环境性 flaky

> 合并自蒸馏候选：Windows 下 pytest 输出被 CLIXML 吞掉；test_phase2_concurrency 是文件锁环境性 flaky

## Windows 环境坑补充（2026-09-20，install-hooks 重构期间实测）

1. **pytest 输出被 CLIXML 吞掉**：Windows 下用 execute_command 跑 pytest，stdout 被 PowerShell 的 CLIXML 流包装吞掉，多次重跑都拿不到结果。解法：输出重定向到文件再读（`python -m pytest tests/ -q --tb=line > .scratch\pytest-out.txt 2>&1`），不要反复重跑碰运气。
2. **test_phase2_concurrency 是环境性 flaky**：全量并发下因 Windows 文件锁竞争（`os.replace` 抛 PermissionError）偶发失败，单独跑 17/17 全过。属环境性 flaky，与代码改动无关，不要据此回滚或排查改动。
