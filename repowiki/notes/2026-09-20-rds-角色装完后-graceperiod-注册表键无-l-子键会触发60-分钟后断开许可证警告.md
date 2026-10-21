---
type: pitfall
title: RDS 角色装完后 GracePeriod 注册表键无 L$ 子键会触发「60 分钟后断开」许可证警告
tags:
- currentcontrolset
- graceperiod
- pitfall
- termservice
metadata:
  date: 2026-09-20
  confidence_level: weak
  source_session: 575221042e1e4a71b69f2e05be56bed8
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-4f79bd.md
  scene: 内部服务器运维
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.10.1
  at: 2026-09-20 11:35:47+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:00:08Z'
---

## 背景

一台 Windows Server 2019 Datacenter 安装 RDS 会话主机角色后，用户 RDP 登录即报「你的远程桌面许可证出现问题，你的会话将在 60 分钟后断开连接」，此时明明处于 120 天宽限期内。

## 现象与根因

`HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\RCM\GracePeriod` 键下没有 `L$` 开头的宽限期记录子键（正常应有一个存储到期时间的子键）。可能是镜像/克隆系统残留。授权服务找不到宽限期记录，按「无许可证且无宽限期」处理，给每个会话发 60 分钟断开警告。

该键默认只有 SYSTEM 权限，管理员也读不了/删不了，需通过以 SYSTEM 身份运行的计划任务（或 psexec）提权删除。

## 正确做法

1. 以 SYSTEM 权限删除 `GracePeriod` 键（例如注册计划任务以 SYSTEM 运行删除脚本）。
2. 重启 TermService 或整机重启，让授权服务重新生成宽限期记录，120 天从重建时刻重新计算。
3. 验证：键下出现 `L$` 子键、登录不再弹 60 分钟警告。

## Rationale

这是实际踩到并定位到的非显而易见故障：报错文案指向「许可证问题」，容易误判为需要立即购买 CAL，真正根因是宽限期记录缺失。删键重建即可修复，值得留档避免重复排查。

## 注意

- 只重启 TermService 可能不够（实测键重建但子键仍为空），必要时做完整重启。
- 重启会断开所有 RDP 会话，执行前需确认；整机重启后若长时间（15 分钟+）网络不可达，需带外管理口/现场排查，远程侧无法继续。
