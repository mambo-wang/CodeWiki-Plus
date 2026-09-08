---
name: windows-python-release
description: 当在 Windows 上手动发布 Python 包或创建 GitHub Release 时——中文提交信息乱码、dist 残留被一并上传、Release 正文乱码、无 gh CLI 取不到凭据——先同步四处版本引用并清理 dist 精确指定产物，中文与结构化输入一律落 UTF-8 文件或用 Python subprocess 精确传，绕开 shell 中间层
type: Skill
status: draft
generated:
  by: codewiki/5.8.0
  at: "2026-09-08T06:04:10Z"
stale_after: 2026-12-07
metadata:
  summary: Windows 手动发布 Python 包的版本同步、dist 清理与 shell 编码绕法 SOP
  source_refs: ["wiki/scenarios/发布与依赖治理方法.md"]
  revisions:
    - at: "2026-09-08T06:04:10Z"
      reason: created from candidate materials
      source: skill_creator
---

## 工作场景

在 Windows（PowerShell/cmd）上手动发布 Python 包到 PyPI / GitHub Release，或提交中文 commit message、给交互式命令喂 stdin 的场景。典型触发：发新版本、写 release notes、环境无 gh CLI 需复用 GCM 凭据调 GitHub API。

## 适用条件

- 发布是手动流程（CI 只做测试与 lint，不负责发布）
- 环境无 gh CLI / 未配置 GH_TOKEN，但 git credential manager 已保存凭证
- 提交信息或 Release 正文含中文/emoji

## 核心 SOP

1. **版本同步四处再 bump**：`pyproject.toml`、包 `__init__.py`、`uv.lock`、MCP server 入口（版本从 `__version__` 注入，勿手写常量）。提交信息用 `chore: bump version to X`，tag 用 lightweight `vX.Y.Z`。
2. **发布闸门**：全量 pytest 通过 + 构建成功。
3. **清 dist/ 再发布**：删除旧产物，或精确指定 `uv publish dist/<pkg>-<version>*`——默认行为是上传 dist/ 下全部产物。
4. 发布后用 PyPI JSON API 核对真实上传版本。
5. **中文提交信息走文件**：`git commit -F <utf8-message-file>`，不要用 `-m` 传中文。
6. **无 gh CLI 取凭据**：用 Python `subprocess` 直调 `git credential fill`（stdin 精确给 `protocol=https\nhost=github.com\n\n`），再调 GitHub REST API；凭证只留进程内，不落盘不打印。
7. Release 正文经 API 创建时请求体显式 UTF-8 编码，去掉任何 GBK 中间解码环节。
8. 控制台输出含非 GBK 字符时设 `PYTHONIOENCODING=utf-8`；生成的 `.ps1` 必须带 UTF-8 BOM，`.sh` 必须无 BOM。

## 判断逻辑

- 乱码、拆词、stdin 为空三者同源：都是 cmd/PowerShell 中间层破坏参数与编码。统一绕法是「落文件 / 精确 subprocess」，不是加转义。
- 乱码一旦产生即不可逆（UTF-8 字节被按 GBK 解码写入，字符永久丢失），只能基于 `git log <old>..<new>` 的事实重写，并标注哪些措辞是推补、请用户核对。
- PyPI 只增不改会幂等跳过已存在文件，但这是侥幸，不是安全网。

## 禁忌与反模式

- 不要 `git commit -m "中文"`（乱码或被拆词）
- 不要用 PowerShell 管道或 `cmd /c echo` 给 `git credential fill` 喂 stdin（stdin 常为空、引号被破坏）
- 不要不清 dist/ 就直接 `uv publish`（旧版本产物被一并上传）
- 不要试图反向还原 GBK 乱码文本（字符已丢失，只能重写）

依据: wiki/scenarios/发布与依赖治理方法.md 的「手动发布四处版本引用」「dist 残留被一并上传」「Release 正文乱码不可逆」「Windows 参数与 stdin 编码统一绕法」
