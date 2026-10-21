---
type: procedure
title: Windows Server 开放多人并发 RDP 的完整流程（2 人免授权 / RDS 角色 + CAL 两条路）
tags:
- currentcontrolset
- procedure
- termservice
- windowsfeature
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
  at: 2026-09-20 11:32:50+00:00
stale_after: '2027-04-19'
origin: conversation
verified:
- by: human:iamwangbao-163-com
  at: '2026-10-21T04:00:14Z'
---

## 背景

组内多人需要同时远程桌面使用一台 Windows Server（2019 Datacenter）。Windows Server 默认只允许 2 个并发 RDP 会话（仅限管理用途），超过 2 人必须走 RDS 会话主机角色。

## 决策/正确做法

两条路线：

1. **≤2 人同时在线（免授权）**：注册表 `HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server` 下设 `fDenyTSConnections=0`、`fSingleSessionPerUser=0`，为每人建独立本地账户并加入 `Remote Desktop Users` 组，`Restart-Service TermService -Force` 生效。
2. **不限并发（需 RDS CAL）**：`Install-WindowsFeature -Name RDS-RD-Server -Restart` 安装会话主机角色；再用 `Win32_TerminalServiceSetting`（namespace `root\cimv2\terminalservices`）的 `ChangeMode` 方法设授权模式，**参数名是 `LicensingType`（4 = PerUser），不是 `LicenseServer`/`Mode`**。未购 CAL 有 120 天宽限期，到期（事件日志 EVENT_ID 1126 提醒）后新连接被拒。

验证要点：`TerminalServerMode=1`（应用服务器模式）、`SingleSession=0`、`UserLimit` 为空即不限并发。

远程操作前置：本机 WinRM 客户端需把目标 IP 加入 `WSMan:\localhost\Client\TrustedHosts`（改它需要本机管理员权限，且本机 WinRM 服务必须在运行）；目标服务器只支持 Negotiate 认证时凭据需用机器名/IP 限定。

## Rationale

这是一次完整跑通并验证的多人 RDP 部署，含授权合规边界（120 天宽限期、CAL 采购节点），未来再遇到「给组内多人共用一台 Windows Server」可直接复用，避免重新调研授权限制。

## 注意

- 不要在对话/笔记中保留管理员明文密码；部署后应尽快轮换在对话中出现过的凭据。
- Essentials 版不支持 RDS 会话主机，动手前先确认 `(Get-CimInstance Win32_OperatingSystem).Caption`。
