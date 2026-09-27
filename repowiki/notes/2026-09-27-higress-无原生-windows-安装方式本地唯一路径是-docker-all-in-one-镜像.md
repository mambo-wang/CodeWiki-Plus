---
type: lesson
title: Higress 无原生 Windows 安装方式，本地唯一路径是 Docker all-in-one 镜像
tags:
- lesson
metadata:
  date: 2026-09-27
  confidence_level: shadow
  task_id: AI网关学习
  source_session: 001563e197d54a1491d058b4a65abcd8
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-af8058.md
  scene: AI网关学习
status: deprecated
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-27 07:55:36+00:00
stale_after: 2027-03-26
origin: conversation
reject_reason: 用户拒绝确认
---

## 背景

任务「AI网关学习」中调研 Higress（阿里开源 AI 网关）能否在 Windows 上本地安装运行。

## 结论

Higress **没有原生 Windows 安装方式**。官方本地部署只有一条路——Docker 一条命令启动 all-in-one 镜像：

```bash
mkdir higress; cd higress
docker run -d --rm --name higress-ai -v ${PWD}:/data \
        -p 8001:8001 -p 8080:8080 -p 8443:8443 \
        higress-registry.cn-hangzhou.cr.aliyuncs.com/higress/all-in-one:latest
```

- 8001：控制台 UI；8080/8443：网关 HTTP/HTTPS 入口
- 生产部署走 K8s + Helm，同样不提供 Windows 原生二进制

## 本机环境核查（2026-09-27）

- Docker：未安装；WSL：未启用（`wsl` 命令不存在）
- Windows 10 企业版 1909（build 18363）——**低于 19041，不支持 WSL2**（WSL2 要求 Windows 10 2004+）
- CPU 虚拟化固件已启用，Hyper-V 可用——Docker Desktop 的 Hyper-V 后端是本机唯一可行容器路径

## 决策

用户决定**不安装 Docker**，因此本机无法本地运行 Higress。替代体验路径：官方在线 demo http://demo.higress.io/（控制台）、https://mcp.higress.ai/（MCP Server 平台），或远程 Linux 服务器跑 all-in-one 镜像。

## Rationale

调研结论 + 明确的环境约束（build 18363 无 WSL2）+ 用户决策，后续任何涉及 Higress 或本机容器化部署的讨论可直接引用，避免重复调研。
