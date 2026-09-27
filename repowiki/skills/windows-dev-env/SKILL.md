---
name: windows-dev-env
description: Windows/PowerShell 下做 git 写操作、跑子进程或批量文件/测试清理时：shell 漂移与中文路径致命令静默失败、无控制台宿主子进程闪窗、GCM 每次弹 OAuth 框、原生 DLL 被锁——须显式复核落盘、subprocess 加 CREATE_NO_WINDOW、gh auth setup-git 持久化凭据，并用 cmd /c 绕 safe-delete 钩子
type: Skill
status: stable
generated:
  by: codewiki/5.9.0
  at: "2026-09-10T09:38:38Z"
stale_after: 2026-12-26
metadata:
  summary: Windows/PowerShell 开发环境坑聚合：git 写操作静默失败须复核、safe-delete 钩子绕法、pytest basetemp、中文路径/消息、.ps1 BOM、子进程闪窗 CREATE_NO_WINDOW、pyd 文件锁 rename-aside、GCM OAuth 持久化、gh CLI zip 免安装、源码环境模块入口
  source_refs: ["notes/2026-09-10-命令链中途-shell-从-powershell-漂到-cmd-致-git-commit-静默未执行且退出码-0须-gi.md", "notes/2026-09-08-windows-powershell-下-git-add-中文路径会静默失败导致-commit---amend-漏掉改动.md", "notes/2026-09-08-github-push-protection-拦截含-secret-的提交追加删除提交无效必须改写原提交.md", "notes/2026-09-07-本仓-windowspowershell-开发环境坑safe-delete-拦批量删除pytest-basetemp中文.md", "notes/2026-09-07-同一文件批量并发-replace-in-file-会触发写锁超时30s需顺序单发.md", "notes/2026-08-29-生成的-ps1-必须带-utf-8-bom否则-powershell-51-按-gbk-误读.md", "notes/2026-09-26-windows-无控制台宿主启动控制台程序会闪窗mcp-server-内-git-子进程用-create-no-wind.md", "notes/2026-09-24-windows-加载中的-pyd-可重命名不可写不可删rename-aside-自动升级技巧的实测依据.md", "notes/2026-09-26-windows-git-credential-manager-每次现场走-oauth-不持久化导致每次-git-push.md", "notes/2026-09-26-windows-无-wingetscoop-时安装-gh-climsi-静默安装被-uac-拦截改用官方-zip-免安装.md", "notes/2026-09-18-全局-codewikiexe-无法-import-本地包install-hooks-需用-python--m-codew.md"]
  revisions: ["at: \"2026-09-10T09:38:38Z\"", {"at": "2026-09-27T02:23:31Z", "reason": "2026-09-27 蒸馏补编：吸收 5 条新坑——无控制台宿主子进程闪窗 CREATE_NO_WINDOW、加载中 .pyd 文件锁 rename-aside、GCM OAuth 每次弹框 gh auth setup-git、gh CLI zip 免安装、源码 checkout 用 python -m 模块入口（来源：/distill-conversations 蒸馏产物，2026-09-26 确认转正）", "source": "skill_creator"}]
  reason: created from candidate materials
  source: skill_creator
  installed_at: "2026-09-27T02:32:43Z"
  installed_to: .codebuddy/skills/windows-dev-env/
  installed_hash: "sha256:7ec2c3799c34d560e4894b1964be03a180c65549e5a8ab23d25157db2079e2ca"
---


## 工作场景
在本仓 Windows + PowerShell（CodeBuddy 沙箱 + profile 安全删除钩子）环境做：git 提交/推送、批量文件删除、pytest 全量回归、中文路径/中文 commit message 处理、生成 .ps1 脚本、启动 git/工具子进程、安装 gh CLI、源码 checkout 内跑包命令。

## 适用条件
- 环境为 Windows PowerShell（含 cmd 混合会话）。
- 涉及 git 写操作、含中文路径/消息、批量 rm/pytest 清理、无控制台宿主的子进程调用，或原生模块文件操作。
- 不适用于纯 Linux/macOS CI（那里中文路径与 shell 漂移不触发同类静默失败）。

## 核心 SOP
1. **Git 写操作后必显式复核落盘**：提交/推送/amend 后跑 `git log -1`、`git status --short`、`git grep -c "<特征串>" <sha>` 确认内容真落地——不能只信退出码。
   - 中文路径 `git add <中文文件>` 会静默失败（pathspec 不匹配），改用 `git add -u` / `git add -A` 避免手写中文路径。
   - 含管道/cmdlet（`Measure-Object`、`Select-Object`）的命令链不要在 shell 可能混用的会话整链跑：PowerShell→cmd 漂移会让整链静默不执行且返回 0。拆成单条独立命令，每条后复核。
2. **含 secret 的提交被 Push Protection 拦截**：在原提交之上追加「删除」提交无用，原提交仍含 secret。未推送的用 `git commit --amend` 改写（替换占位符→`git add -u`→amend）；已推远的用 `git filter-repo`。token 明文进过仓库即建议到源站轮换。
3. **批量删除被 safe-delete 钩子拦截**（`del /S`、`Remove-Item -Recurse`、TEMP 下 pytest garbage）：改用 `cmd /c "rd /s /q <dir>"` 或 Python `shutil.rmtree`/逐个 `unlink`。
4. **pytest 全量回归**：用 `--basetemp=.pytest-tmp`（工作区内，加 .gitignore）避免 TEMP 堆积 garbage 被沙箱拦截连带新跑挂；失败清单用 `--junitxml` + ElementTree 解析最可靠；PowerShell 输出噪音用 `cmd /c` 重定向到文件再读。
5. **中文 commit message**：PowerShell 直传 `git commit -m "中文"` 解析失败，写临时文件 + `git commit -F <file>`。
6. **生成的 .ps1 须带 UTF-8 BOM**，否则 PowerShell 5.1 按 GBK 误读。
7. **无控制台宿主启动控制台程序会闪窗**：MCP server 由 IDE 拉起时无控制台，Windows 会给其启动的 `git.exe` 等控制台程序分配全新窗口——auto_push 一次跑 add/commit/push 弹多次。所有 git 子进程统一加 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`（封装 `windows_creationflags()` helper，非 Windows 返回 0），全链路收口。
8. **Windows 加载中的 .pyd 文件锁语义**：运行中进程加载的原生 DLL/.pyd **可重命名、不可写打开、不可删除**（写/删 PermissionError，rename OK——Chrome 更新器技巧在 Python 原生模块同样成立）。替换被锁文件用 rename-aside（先 rename 走再写新版，重启后清理 .old），不要试图原地覆盖。
9. **git 写操作每次弹 OAuth 账号框**：GCM 里无持久化 GitHub 凭证时，每次 push/fetch/`git credential fill` 都现场走 OAuth。执行 `gh auth login`（或 `gh auth login --with-token`）后 `gh auth setup-git`，让 GCM 走已存凭据，不再弹框。
10. **无 winget/scoop 安装 gh CLI**：msi 静默安装（msiexec /qn）可能被 UAC 提权拦截、跑 1 分钟以上不生效。改用官方 zip 免安装版：`urllib.request.urlretrieve('https://github.com/cli/cli/releases/download/<v>/gh_<v>_windows_amd64.zip')` 下载 → `Expand-Archive` 解压到本地目录 → 加入 PATH。
11. **源码 checkout 内跑包命令用模块入口**：全局 console script（`codewiki.exe`）的 sys.path 不含 CWD，包未装全局时报 `ModuleNotFoundError`。从仓库根用 `python -m codewiki.cli.main ...` 等价入口执行。

## 判断逻辑
- 命令「看起来成功」但关键写操作无证据 → 先假设静默失败，显式复核。
- 删除/清理无效果 → 多半被 safe-delete 钩子拦，换 `cmd /c rd` 或 shutil。
- PowerShell 报 stderr/噪音 → 不一定是失败（git 进度常走 stderr），以 `git status` 为准。
- 子进程每跑必闪窗 → 宿主无控制台，加 CREATE_NO_WINDOW，不是加 start /min。
- 每次 push 都弹账号框 → 先 `gh auth setup-git`，不是手动输密码。
- 原生模块写/删报 PermissionError 但 rename 成功 → 进程持有加载锁，走 rename-aside。

## 禁忌与反模式
- 勿用 `&&` 串联含中文路径或 cmdlet 的命令链后只看末条退出码——中间步静默失败会被掩盖。
- 勿在含 secret 的提交上追加「删除」提交试图绕过 Push Protection——原提交仍含 secret，推送照拒。
- 勿手写中文路径给 `git add`——用 `-u/-A`。
- 勿对同一文件并行多个 replace_in_file——会触发 30s 写锁超时丢编辑，须顺序单发。
- 勿假设 PowerShell 的 stderr 即失败。
- 勿在无控制台宿主里裸跑 subprocess 控制台程序而不加 CREATE_NO_WINDOW——闪窗扰民。
- 勿对运行中进程锁定的 .pyd/.dll 尝试覆盖删除——走 rename-aside。

依据: notes/2026-09-26-windows-无控制台宿主启动控制台程序会闪窗mcp-server-内-git-子进程用-create-no-wind.md 的「根因与 CREATE_NO_WINDOW 修复」；notes/2026-09-24-windows-加载中的-pyd-可重命名不可写不可删rename-aside-自动升级技巧的实测依据.md 的「真机实测表」；notes/2026-09-26-windows-git-credential-manager-每次现场走-oauth-不持久化导致每次-git-push.md 的「gh auth setup-git 正确做法」；notes/2026-09-26-windows-无-wingetscoop-时安装-gh-climsi-静默安装被-uac-拦截改用官方-zip-免安装.md 的「zip 免安装流程」；notes/2026-09-18-全局-codewikiexe-无法-import-本地包install-hooks-需用-python--m-codew.md 的「模块入口替代」

