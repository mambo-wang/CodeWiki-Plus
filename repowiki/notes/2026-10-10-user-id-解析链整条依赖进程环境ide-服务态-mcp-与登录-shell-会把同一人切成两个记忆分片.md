---
type: pitfall
title: user_id 解析链整条依赖进程环境：IDE 服务态 MCP 与登录 shell 会把同一人切成两个记忆分片
tags:
- pitfall
aliases:
- user_id 漂移
- 记忆分片分裂
- per-user shard 不一致
- Administrator 分片
metadata:
  date: 2026-10-10
  confidence_level: strong
  task_id: 产品维护
  severity: high
  root_cause: user_id 的每一环都是进程环境的函数：机器缓存路径在 import 期由 APPDATA or expanduser('~') 定死，git
    配置要靠 HOME 才找得到 ~/.gitconfig。IDE 启的 MCP server 是服务态进程，两者同时不可用就退到 os.getlogin()，与登录
    shell 解出的邮箱身份分裂成两个 uid。
  reason: 受控环境矩阵 + MCP cwd 实测定位根因；B+C+D 已实施并真机复验，口径由 draft 升为 high
  verification:
    test_ref: tests/test_team_telemetry.py::TestRepoIdentityPin
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.14.1
  at: 2026-10-10 06:24:35+00:00
stale_after: '2027-04-08'
verified:
- by: human:mambo-wang
  at: '2026-10-10T09:47:37Z'
---

## 背景
任务记忆按 `memories/<user_id>.md` 分片，文件所有权即 git 级互斥原语；压缩/检索/写入检查都以「当前调用者的分片」为域（file-domain, author-exclusive）。同一个人若被解成两个 uid，读写域就分裂。

## 现象（本仓实测）
- 同一个任务 `产品维护` 下同时存在 `memories/Administrator.md`（MCP 通道写）与 `memories/iamwangbao-163-com.md`（CLI/进程内写），get_task_context 把后者渲染成「其他成员记忆」。
- `repowiki/.meta/telemetry/` 下 6 个身份分片：Administrator / iamwangbao-163-com / local / mambo-wang / wandering-bug / wangbao——同一台机器多年漂移的沉积物。
- 压缩链实测后果：MCP 侧 prepare 返回 `compaction_needed=false, entries_to_compress=[]`，磁盘实有 45 条——分片归属不匹配时压缩静默空转（不变量本身正确，使用者看到「压不动」）。

## 根因
身份解析的每一环都以**进程环境**为输入，而两条通道的环境天然不同：

- 机器缓存路径在 **import 期**定死：`_USER_ID_CACHE_PATH = os.environ.get("APPDATA") or os.path.expanduser("~")` + `.codewiki_user_id`（`codewiki/src/config.py:220`）。APPDATA 缺失的进程于是读写的是**另一个文件**——本机曾同时存在 `%APPDATA%\.codewiki_user_id`=正主邮箱 与 `%USERPROFILE%\.codewiki_user_id`=`Administrator` 两份缓存，这就是「同一台机器两个身份」的物理形态。
- `_git_config_value("user.email")`（`config.py:149`）靠 subprocess 调 `git`：**git 需要 HOME 才找得到 `~/.gitconfig`**，服务态进程 HOME 不可用 → 全局配置读不到 → 返回 `''`；PATH 里没有 git 同理。
- 两者同时落空 → `os.getlogin()` = Windows 登录名（本机 `Administrator`）。

## 实证
1. 受控环境矩阵（同一条解析链，逐子进程改环境变量）：仅登录 shell 与「APPDATA 缺失 + HOME 改写」两格分别得到 `iamwangbao-163-com` 与 `Administrator`；只去 git、或只改 HOME（APPDATA 仍在）都不漂移——**缓存是唯一的兜底，它和 git 配置同时不可用才退到 getlogin**。
2. MCP server 的 cwd 被实测为 `C:\Users\Administrator\AppData\Local\Programs\Qoder CN`（不传 repo_path 时笔记直接落到那个目录的 repowiki/）——即它确实是服务态进程，不是登录 shell 环境。

## 影响面
1. 记忆分片分裂：同一人被切成两个文件，热层/温层渲染错位（自己的条目以「其他成员」身份注入）。
2. 压缩/检索/写入检查在错误的分片域上静默空转。
3. near-duplicate 拦截（difflib>0.85）比对范围限自己的分片 → 跨分片重复不再被拦。
4. telemetry/采纳计数按 uid 分片，指标被稀释。

## 已实施的修复（2026-10-10，方案 B+C+D）
把身份钉在「两条通道必然共享的东西」上，并让漂移当场可见：

- **仓库本地身份钉** `repowiki/.meta/user_id`（gitignored、已登记 `TEAM_LAYOUT_REBUILDABLE_FILES`，删掉即重新派生）：新链 `CODEWIKI_USER` env > **pin** > `git -C <output_dir> config user.email` > `user.name` > 机器缓存 > `os.getlogin()` > `local`（`resolve_user_id(output_dir) -> (uid, source)`，`config.py:296`）。
- **只有 git 当场验证过的身份允许写钉/写缓存**。次序上 git 刻意排在缓存之前：缓存只是过去一次派生的备忘，可能是某次退化通道的登录名兜底；让过去的猜测压过当下可读的 git 配置，会把错误身份永久钉回克隆。
- 读钉时净化（uid 会进文件名，外部塞的钉不得带路径分隔符）；无 `output_dir` 时跳过钉、仍可解析。
- **C 可见性**：`get_task_context` 与 `add_task_memory` 回显 `user` + `user_source`（`env|pin|git-email|git-name|cache|login|local`），来源意外即该通道漂移了；6 处调用点全部传 `output_dir`。
- **D 存量修复**：`memories/Administrator.md` 的 7 条经 `locked_rmw` 原样并入正主分片后删除该文件（幂等、原文已备份）；污染的第二份机器缓存 `%USERPROFILE%\.codewiki_user_id` 已备份后删除。

复验：退化模拟（剥缓存、剥 git、只剩登录名）解析仍得 `('iamwangbao-163-com','pin')`；无钉调用 `resolve_user_id(None)` 得 `git-email`（证明 git 盖过缓存）；MCP 真机回显 `user_source=pin`，他人分片段消失。

## 仍需注意
- 长驻 MCP server 缓存已导入模块：改了 `config.py` 必须 `/mcp reload`，否则新代码导入 `resolve_user_id` 会直接报错（本轮实撞一次）。
- 零代码止血仍有效：两条通道都写死 `CODEWIKI_USER` 可立即对齐（env 优先级最高）。
- 任何 codewiki MCP 调用都显式传 `repo_path`（本次误写就是反例）。
- 未动项：`repowiki/.meta/telemetry/` 的 6 个历史身份分片未合并（采纳计数仍按旧 uid 分散）。
