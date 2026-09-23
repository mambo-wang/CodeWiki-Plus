---
name: windows-python-release
description: 当要手动发布 Python 包（codewiki-plus）到 PyPI 并建 GitHub Release 时——CI 不发布、Windows 控制台为 GBK、可能无 gh CLI、本机网络对 upload.pypi.org 的 Python TLS 握手有干扰——按 8 步主干执行：同步四处版本→bump 提交→pytest+ruff 闸门→清 dist 构建→PR 合并 main→tag merge commit 建 Release→uv publish（TLS 超时则 curl.exe 直传）→PyPI JSON API 核对
---

## 工作场景

手动发布 Python 包（`codewiki-plus`）到 PyPI 并创建 GitHub Release。**CI 只跑测试与 lint，不负责构建与发布**（`.github/workflows/ci.yml:13-74`），因此发布主干没有脚本承载，必须按序手工执行。Windows 控制台默认 GBK，环境可能无 gh CLI。

## 适用条件

- 发布是手动流程，仓库无发布脚本
- 提交信息或 Release 正文含中文/emoji
- 环境无 gh CLI / 未配置 GH_TOKEN，但 git credential manager 已保存凭据

## 核心 SOP

按序执行 8 步，**每步有判定点，不通过就停，不要带着问题往下走**。

1. **同步四处版本引用**：`pyproject.toml`（`version`）、`codewiki/__init__.py`（`__version__`）、`uv.lock`、`codewiki/mcp/server.py`（`version=__version__` 注入，勿手写常量）。CLI 与 actor id 也从 `__version__` 读取，自动跟随。
   判定点：四处版本字符串完全一致。

2. **提交 bump 并推送 develop**：消息 `chore: bump version to X`；推 `origin develop`。
   判定点：`git show` 确认版本改动齐全。
   ⚠️ 中文提交信息用 `git commit -F <utf8 文件>`，**不要用 `-m`**（GBK 破坏，乱码或拆词）。

3. **发布闸门**：`pytest -q` 全绿；`ruff check` / `ruff format --check` 通过。
   判定点：无失败用例，无 lint 错误。

4. **构建并清理产物**：`uv build`；发布前**清 `dist/`** 或只精确指定本次产物。
   判定点：`dist/` 下只剩本次版本的 wheel 与 sdist。
   ⚠️ 不清 `dist/` 会连带上传旧产物（5.6.0 发布时残留 6 个）。

5. **合并 main**：建 PR develop→main（无 gh CLI 时用 Python `subprocess` 调 `git credential fill` 取凭据再调 REST API，请求体显式 UTF-8）；轮询 head sha 的 **check-runs**（不是 commit status）等 CI 绿后合并。
   判定点：PR merged，main 含 bump commit。

6. **打 tag 并建 GitHub Release**：lightweight tag `vX.Y.Z` 打在 **PR merge commit 上（main 分支）**——Release 应反映 main 的事实状态；不要打在 develop 的 bump commit 上（v5.12.0 旧做法，与 Release 所属分支不一致）。Release 正文经 REST API 创建，显式 UTF-8。
   ⚠️ Release 正文乱码**不可逆**（UTF-8 被按 GBK 解码写入，字符永久丢失），只能基于 `git log` 事实重写。
   ⚠️ 给 `git credential fill` 喂 stdin 不用 PowerShell 管道（stdin 常为空、引号被破坏），用 `subprocess` 精确传字节；凭据只留进程内。

7. **发布到 PyPI**：优先 `uv publish dist/codewiki_plus-<version>*`（精确指定，默认传 dist/ 全部）。
   ⚠️ **本机网络对 upload.pypi.org 的 Python OpenSSL TLS 握手会被干扰**：uv publish / twine / requests 全部连接超时（TCP 通、curl 秒通）。绕法：curl.exe（schannel 栈）直传 legacy API——Python 从 whl 的 `*.dist-info/METADATA`、sdist 的 `PKG-INFO` 提取元数据构造完整表单（`:action=file_upload`、`protocol_version=1`、`filetype`、`pyversion` + 全部元数据字段 + `description` 正文），写 curl `-K` 配置文件（`form-string`，命令行会超长），`-u __token__:<token>` POST。**digest 字段名是 `sha256_digest`**（不是 `digests_sha256`，400 报 missing digest）。token 经参数传进程内，用完删临时文件。

8. **核对真实上传**：`https://pypi.org/pypi/codewiki-plus/json` 查最新版本（JSON API 有缓存延迟，可直接查 `/pypi/codewiki-plus/<version>/json`）。
   判定点：API 返回版本 == 目标版本，双产物 size 正确。

## 判断逻辑

- **主干优先**：先有完整流程，避坑是各步的注解，不是流程的替代品。缺任何一步（尤其是 3 闸门与 8 核对）都不算发布完成。
- 乱码/拆词/stdin 失效同源：都是 cmd/PowerShell 中间层破坏参数与编码。统一绕法是「落文件 / 精确 subprocess」，不是加转义。
- TLS 握手超时先做栈归因：TCP 通 + curl（schannel）通 + Python requests 超时 → 是 OpenSSL 栈被网络层干扰，换传输栈（curl.exe）而不是加超时重试。
- PyPI 只增不改会幂等跳过已存在文件，但这是侥幸，不是安全网。

## 禁忌与反模式

- 不要 `git commit -m "中文"`
- 不要不清 `dist/` 就直接 `uv publish`
- 不要跳过闸门（步骤 3）或发布后核对（步骤 8）
- 不要用 PowerShell 管道或 `cmd /c echo` 给 `git credential fill` 喂 stdin
- 不要试图反向还原 GBK 乱码文本（字符已丢失，只能重写）
- PyPI 上传超时不要盲目加超时重试——先区分是读取慢（加超时有用）还是 TLS 握手被掐（换 curl.exe）
- 不要把 PyPI token 写进任何落盘文件后不清理

依据: notes/2026-09-10-codewiki-手动发布完整流程同步四处版本测试build清distpublishrelease核对.md 的「7 步主干与每步判定点」；wiki/scenarios/发布与依赖治理方法.md 的「dist 残留被一并上传」「Release 正文乱码不可逆」「Windows 参数与 stdin 编码统一绕法」；任务「发版本」v5.13.0 发布实操（2026-09-23）：TLS 握手干扰归因与 curl.exe 绕法、sha256_digest 字段名、tag 打在 merge commit 的约定
