---
name: windows-python-release
description: 当要手动发布 Python 包（codewiki-plus）到 PyPI 并建 GitHub Release 时——CI 不发布、Windows 控制台为 GBK、可能无 gh CLI——按 7 步主干执行：同步四处版本→bump 提交→pytest+build 闸门→清 dist→uv publish→建 Release→PyPI JSON API 核对
type: Skill
status: draft
generated:
  by: codewiki/5.8.0
  at: "2026-09-08T06:04:10Z"
stale_after: 2026-12-09
metadata:
  summary: 手动发布 7 步主干 SOP + 每步避坑注解
  source_refs: ["wiki/scenarios/发布与依赖治理方法.md", "notes/2026-09-10-codewiki-手动发布完整流程同步四处版本测试build清distpublishrelease核对.md"]
  revisions: ["at: \"2026-09-08T06:04:10Z\"", {"at": "2026-09-10T02:02:25Z", "reason": "按主干优先重构：原 SOP 8 步中 6 步是避坑，缺发布主流程；改为 7 步主干（每步带判定点），避坑降级为步骤注解。来源为新增的流程型笔记。", "source": "skill_creator"}]
  reason: created from candidate materials
  source: skill_creator
---

## 工作场景

手动发布 Python 包（`codewiki-plus`）到 PyPI 并创建 GitHub Release。**CI 只跑测试与 lint，不负责构建与发布**（`.github/workflows/ci.yml:13-74`），因此发布主干没有脚本承载，必须按序手工执行。Windows 控制台默认 GBK，环境可能无 gh CLI。

## 适用条件

- 发布是手动流程，仓库无发布脚本
- 提交信息或 Release 正文含中文/emoji
- 环境无 gh CLI / 未配置 GH_TOKEN，但 git credential manager 已保存凭据

## 核心 SOP

按序执行 7 步，**每步有判定点，不通过就停，不要带着问题往下走**。

1. **同步四处版本引用**：`pyproject.toml`（`version`）、`codewiki/__init__.py`（`__version__`）、`uv.lock`、`codewiki/mcp/server.py`（`version=__version__` 注入，勿手写常量）。CLI 与 actor id 也从 `__version__` 读取，自动跟随。
   判定点：四处版本字符串完全一致。

2. **提交 bump 并打 tag**：消息 `chore: bump version to X`；lightweight tag `vX.Y.Z`（与历史一致）。
   判定点：`git show` 确认版本改动齐全。
   ⚠️ 中文提交信息用 `git commit -F <utf8 文件>`，**不要用 `-m`**（GBK 破坏，乱码或拆词）。

3. **发布闸门**：`uv run pytest --cov=codewiki --cov-report=term-missing -p no:cacheprovider tests/ -q` 全绿；`ruff check` / `ruff format --check` 通过。
   判定点：无失败用例，无 lint 错误。

4. **构建并清理产物**：`uv build`；发布前**清 `dist/`** 或只精确指定本次产物。
   判定点：`dist/` 下只剩本次版本的 wheel 与 sdist。
   ⚠️ 不清 `dist/` 会连带上传旧产物（5.6.0 发布时残留 6 个）。

5. **发布到 PyPI**：`uv publish dist/codewiki-plus-<version>*`。
   ⚠️ `uv publish` 默认上传 `dist/` 下**全部**产物，必须精确指定。

6. **创建 GitHub Release**：有 gh CLI 用 `gh release create`；无 gh CLI 时用 Python `subprocess` 调 `git credential fill` 取凭据再调 REST API，请求体显式 UTF-8。
   ⚠️ Release 正文乱码**不可逆**（UTF-8 被按 GBK 解码写入，字符永久丢失），只能基于 `git log` 事实重写，不要试图反向还原。
   ⚠️ 给 `git credential fill` 喂 stdin 不用 PowerShell 管道（stdin 常为空、引号被破坏），用 `subprocess` 精确传字节；凭据只留进程内。

7. **核对真实上传**：`https://pypi.org/pypi/codewiki-plus/json` 查最新版本。
   判定点：API 返回版本 == 目标版本。

## 判断逻辑

- **主干优先**：先有完整流程，避坑是各步的注解，不是流程的替代品。缺任何一步（尤其是 3 闸门与 7 核对）都不算发布完成。
- 乱码/拆词/stdin 失效同源：都是 cmd/PowerShell 中间层破坏参数与编码。统一绕法是「落文件 / 精确 subprocess」，不是加转义。
- PyPI 只增不改会幂等跳过已存在文件，但这是侥幸，不是安全网。

## 禁忌与反模式

- 不要 `git commit -m "中文"`
- 不要不清 `dist/` 就直接 `uv publish`
- 不要跳过闸门（步骤 3）或发布后核对（步骤 7）
- 不要用 PowerShell 管道或 `cmd /c echo` 给 `git credential fill` 喂 stdin
- 不要试图反向还原 GBK 乱码文本（字符已丢失，只能重写）

依据: notes/2026-09-10-codewiki-手动发布完整流程同步四处版本测试build清distpublishrelease核对.md 的「7 步主干与每步判定点」；wiki/scenarios/发布与依赖治理方法.md 的「dist 残留被一并上传」「Release 正文乱码不可逆」「Windows 参数与 stdin 编码统一绕法」
