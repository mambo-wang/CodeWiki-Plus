---
type: pitfall
title: build 后端 setuptools→hatchling 迁移后 wheel 内容会变化，需对比文件清单而非只看能否安装
tags:
- '16'
- pitfall
metadata:
  date: 2026-08-26
  related_modules:
  - codewiki
  severity: medium
  consolidated_into:
  - wiki/scenarios/发布与依赖治理方法.md
status: stable
generated:
  by: codewiki/5.4.3
  at: 2026-08-25 16:38:44+00:00
stale_after: 2027-02-22
author: wandering-bug
---

## 背景

PR #16 将 build 后端从 setuptools（显式 `packages` 列表 20 项 + `package-data`）迁移到 hatchling（`packages=["codewiki"]` 自动发现 + `[tool.hatch.build] artifacts`）。评审时逐一对比 wheel 内容才发现行为差异。

## 正确做法

迁移 build 后端后，用 `python -m build`（或 `pip wheel .`）实际构建，`unzip -l <wheel>` 对比新旧 wheel 文件清单，重点核对：

- 数据文件：setuptools `package-data` 的 glob 是**单层**匹配（`agents/*.md` 只含一级子目录），hatchling `artifacts` 的 `agents/**/*` 是递归——覆盖范围可能扩大；
- 嵌套包：hatchling 自动发现要求每个包目录有 `__init__.py`，无该文件的目录会被漏掉（或反过来，多了 setuptools 显式列表之外的包）。

## 根因

两套语义互不报错地产生不同 wheel。本案例中 `codewiki/hooks.yaml` 被 setuptools `package-data` 漏掉（wheel 一直缺失，而 `hook_registry.py` 运行时加载它），hatchling 自动包含实为隐性修复——对 pip 安装用户是未声明的行为变化，评审应指出并让 PR 描述补充说明。

## 适用范围

任何 build 后端/打包配置变更；PR 声称"对安装用户无影响"时，必须用 wheel 清单验证而非假设。
