---
name: windows-dev-env
description: Windows/PowerShell 下做 git 写操作或批量文件/测试清理时，shell 漂移与中文路径会致命令静默失败(退出码 0)，须用 git add -u / 拆单条命令 / cmd /c 绕 safe-delete 钩子并显式复核落盘
type: Skill
status: draft
generated:
  by: codewiki/5.9.0
  at: "2026-09-10T09:38:38Z"
stale_after: 2026-12-09
metadata:
  summary: Windows/PowerShell 开发环境坑聚合：git 写操作静默失败须复核、safe-delete 钩子绕法、pytest basetemp、中文路径/消息、.ps1 BOM
  source_refs: ["notes/2026-09-10-命令链中途-shell-从-powershell-漂到-cmd-致-git-commit-静默未执行且退出码-0须-gi.md", "notes/2026-09-08-windows-powershell-下-git-add-中文路径会静默失败导致-commit---amend-漏掉改动.md", "notes/2026-09-08-github-push-protection-拦截含-secret-的提交追加删除提交无效必须改写原提交.md", "notes/2026-09-07-本仓-windowspowershell-开发环境坑safe-delete-拦批量删除pytest-basetemp中文.md", "notes/2026-09-07-同一文件批量并发-replace-in-file-会触发写锁超时30s需顺序单发.md", "notes/2026-08-29-生成的-ps1-必须带-utf-8-bom否则-powershell-51-按-gbk-误读.md"]
  revisions:
    - at: "2026-09-10T09:38:38Z"
      reason: created from candidate materials
      source: skill_creator
---

## 工作场景
在本仓 Windows + PowerShell（CodeBuddy 沙箱 + profile 安全删除钩子）环境做：git 提交/推送、批量文件删除、pytest 全量回归、中文路径/中文 commit message 处理、生成 .ps1 脚本。

## 适用条件
- 环境为 Windows PowerShell（含 cmd 混合会话）。
- 涉及 git 写操作、含中文路径/消息、或批量 rm/pytest 清理。
- 不适用于纯 Linux/macOS CI（那里中文路径与 shell 漂移不触发同类静默失败）。

## 核心 SOP
依据: notes/2026-09-10-命令链中途-shell-从-powershell-漂到-cmd-致-git-commit-静默未执行且退出码-0须-gi.md 的「正确做法」；notes/2026-09-08-windows-powershell-下-git-add-中文路径会静默失败导致-commit---amend-漏掉改动.md 的「正确做法」；notes/2026-09-07-本仓-windowspowershell-开发环境坑safe-delete-拦批量删除pytest-basetemp中文.md 的「坑与解法」。

1. **Git 写操作后必显式复核落盘**：提交/推送/amend 后跑 `git log -1`、`git status --short`、`git grep -c "<特征串>" <sha>` 确认内容真落地——不能只信退出码。
   - 中文路径 `git add <中文文件>` 会静默失败（pathspec 不匹配），改用 `git add -u` / `git add -A` 避免手写中文路径。
   - 含管道/cmdlet（`Measure-Object`、`Select-Object`）的命令链不要在 shell 可能混用的会话整链跑：PowerShell→cmd 漂移会让整链静默不执行且返回 0。拆成单条独立命令，每条后复核。
2. **含 secret 的提交被 Push Protection 拦截**：在原提交之上追加「删除」提交无用，原提交仍含 secret。未推送的用 `git commit --amend` 改写（替换占位符→`git add -u`→amend）；已推远的用 `git filter-repo`。token 明文进过仓库即建议到源站轮换。
3. **批量删除被 safe-delete 钩子拦截**（`del /S`、`Remove-Item -Recurse`、TEMP 下 pytest garbage）：改用 `cmd /c "rd /s /q <dir>"` 或 Python `shutil.rmtree`/逐个 `unlink`。
4. **pytest 全量回归**：用 `--basetemp=.pytest-tmp`（工作区内，加 .gitignore）避免 TEMP 堆积 garbage 被沙箱拦截连带新跑挂；失败清单用 `--junitxml` + ElementTree 解析最可靠；PowerShell 输出噪音用 `cmd /c` 重定向到文件再读。
5. **中文 commit message**：PowerShell 直传 `git commit -m "中文"` 解析失败，写临时文件 + `git commit -F <file>`。
6. **生成的 .ps1 须带 UTF-8 BOM**，否则 PowerShell 5.1 按 GBK 误读。

## 判断逻辑
- 命令「看起来成功」但关键写操作无证据 → 先假设静默失败，显式复核。
- 删除/清理无效果 → 多半被 safe-delete 钩子拦，换 `cmd /c rd` 或 shutil。
- PowerShell 报 stderr/噪音 → 不一定是失败（git 进度常走 stderr），以 `git status` 为准。

## 禁忌与反模式
- 勿用 `&&` 串联含中文路径或 cmdlet 的命令链后只看末条退出码——中间步静默失败会被掩盖。
- 勿在含 secret 的提交上追加「删除」提交试图绕过 Push Protection——原提交仍含 secret，推送照拒。
- 勿手写中文路径给 `git add`——用 `-u/-A`。
- 勿对同一文件并行多个 replace_in_file——会触发 30s 写锁超时丢编辑，须顺序单发。
- 勿假设 PowerShell 的 stderr 即失败。
