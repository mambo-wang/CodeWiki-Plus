---
type: lesson
title: CodeWiki 手动发布完整流程：同步四处版本→测试→build→清dist→publish→Release→核对
tags:
- codewiki
- github
- lesson
aliases:
- 发版本流程
- release SOP
- 手动发布流程
metadata:
  date: 2026-09-10
  task_id: 技能提取
  related_modules:
  - release
  - ci
  compiled_into:
  - skills/windows-python-release/SKILL.md
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.8.0
  at: 2026-09-10 02:01:17+00:00
stale_after: '2027-03-09'
verified:
- by: human:wangbao
  at: '2026-09-10T02:01:31Z'
---

## 事实

CodeWiki-CN（包名 `codewiki-plus`）的 PyPI / GitHub Release 发布是**手动流程**：CI 只跑测试与 lint，不负责构建与发布（`.github/workflows/ci.yml:13-74`）。因此发布主干只存在于操作者脑子里，没有脚本承载。

## 完整流程（按执行顺序，7 步主干）

1. **同步四处版本引用**：`pyproject.toml`（`version` 字段）、`codewiki/__init__.py:8`（`__version__`）、`uv.lock`、`codewiki/mcp/server.py:96`（`version=__version__`，从 `__init__` 注入，勿手写常量）。CLI 与 actor id 也从 `__version__` 读取，自动跟随。
2. **提交 bump**：`git commit -F <utf8 消息文件>`（中文信息不能走 `-m`），消息 `chore: bump version to X`；打 **lightweight** tag `vX.Y.Z`（与历史一致）。
3. **发布闸门**：`uv run pytest --cov=codewiki --cov-report=term-missing -p no:cacheprovider tests/ -q` 全绿（CI 同款命令，`ci.yml:33`）；`ruff check` / `ruff format --check` 通过。判定点：全绿 + 无失败用例。
4. **构建并清理产物**：`uv build`；发布前**清空 `dist/`** 或只精确指定本次产物。判定点：`dist/` 下只有本次版本的 wheel 与 sdist。
5. **发布到 PyPI**：`uv publish dist/codewiki-plus-<version>*`（`uv publish` 默认上传 `dist/` 下**全部**产物）。
6. **建 GitHub Release**：有 gh CLI 用 `gh release create`；无 gh CLI 时用 Python `subprocess` 取 `git credential fill` 再调 REST API，请求体显式 UTF-8。
7. **核对真实上传**：`https://pypi.org/pypi/codewiki-plus/json` 查最新版本。判定点：API 返回版本 == 目标版本。

## 每步判定点（失败即停，不要继续下一步）

- 步 1：四处版本号字符串完全一致
- 步 3：pytest 全绿、ruff 无错
- 步 4：`dist/` 只剩本次产物
- 步 7：PyPI JSON API 的版本等于目标版本

## 已知避坑（是上面各步的注解，不是主干）

- 步 2：Windows 下 `git commit -m "中文"` 会乱码或被拆词 → 用 UTF-8 消息文件 + `-F`。
- 步 4：不清 `dist/` 会连带上传旧版本产物（5.6.0 发布时残留 6 个旧产物）。
- 步 6：Release 正文乱码**不可逆**（UTF-8 被按 GBK 解码写入，字符永久丢失），只能基于 `git log` 事实重写；不要试图反向还原。
- 步 6：给 `git credential fill` 喂 stdin 不用 PowerShell 管道（`stdin` 常为空、引号被破坏），用 `subprocess` 精确传字节。

## 备注

本条为「流程型」知识，临时借道 `lesson` 类型做下游验证（验证目的是确认技能编译能否产出完整主干，而非仅有避坑条目）。
