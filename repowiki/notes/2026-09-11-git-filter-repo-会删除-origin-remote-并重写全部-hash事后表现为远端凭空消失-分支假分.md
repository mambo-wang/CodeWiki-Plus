---
type: pitfall
title: "git filter-repo 会删除 origin remote 并重写全部 hash，事后表现为「远端凭空消失 + 分支假分叉」"
tags: ["codewiki", "pitfall"]
aliases: ["filter-repo 删 remote", "filter-repo 后 push 被拒", "假分叉", "ref-map 反查 clone 来源", "remote 配置消失", "non-fast-forward 误判"]
metadata:
  date: 2026-09-11
  severity: high
  root_cause: "git filter-repo 的设计行为：为防止把重写后的历史误推到尚未重写的旧历史仓，它会主动移除 remote 配置（含 origin）并重写所有 ref；重写后的提交与远端同名分支失去共同祖先，于是表现为「分支分叉」。"
status: stable
author: iamwangbao-163-com
generated: { by: codewiki/5.9.0, at: 2026-09-11T05:51:16Z }
stale_after: 2027-03-10
source_conversations: ['raw\conv-继续调研.md']

---

## 背景

2026-09-11 上午 9:30 对 `d:/repos/CodeWiki-CN`（`mambo-wang/CodeWiki-Plus` 的克隆）跑 `git filter-repo` 清理历史中的密钥。之后想推送时代价是：

- `git remote -v` 里 `origin`（CodeWiki-Plus）**消失了**，只剩后来手动加的 `upstream`（官方上游 FSoft-AI4Code/CodeWiki）
- 直接 `git push` 报 non-fast-forward
- `git rev-list --left-right --count` 显示「远端独有 455 / 本地独有 499」，看起来像两条独立演进线走了 11 个月

用户的第一反应是「我是不是推错仓库了」——这是最容易踩的误判：**remote 只剩一个 upstream（第三方上游）时，很容易以为自己一直在推错地方。**

## 结论

`filter-repo` 做的两件事都是它的**设计行为**，不是故障：

1. **主动删除 remote**（含 `origin`）——防止你把重写后的历史误推到尚未重写的旧历史仓。
2. **重写全部提交 hash**——重写后的提交与远端同名分支没有共同祖先，于是表现为「分支分叉」。

**区分「重写」与「真分叉」的判断依据是内容差异规模**：相隔 11 个月、455 vs 499 个提交的两条线，`git diff --stat` 却只差 60 个文件 / +7016 / -101 行——这不可能是独立演进，只能是同一条线的新旧两套 hash。

## 诊断手段

`.git/filter-repo/ref-map` 存着重写前后的 hash 对照（覆盖所有 ref）。把它的 old 列与远端各分支当前值逐一比对即可确认：

| 分支 | ref-map old | 远端当前 | 吻合 |
|---|---|---|---|
| `main` | `0b49984c` | `0b49984c` | ✓ |
| `0.0` | `f7ed709e` | `f7ed709e` | ✓ |
| `develop_weknora` | `9f3679f0` | `9f3679f0` | ✓ |
| `team-memory` | `36002017` | `36002017` | ✓ |
| `refactor/split-server-monolith` | `13face27` | `13face27` | ✓ |

9 个分支全部对上 → 确认这个副本就是该远端的克隆。**`ref-map` 是事后反查「这个副本从哪来」的唯一可靠凭据**（remote 配置已被删，`git reflog` 里的 remote 记录也没了）。

同目录其他文件：`commit-map`（逐提交 old→new 对照）、`already_ran`（存在则再次运行必须加 `--force`）、`changed-refs`、`first-changed-commits`。**这些文件的 mtime 就是 filter-repo 的执行时间**，是与用户对时间线时最有力的证据。

## 恢复步骤

```bash
git remote add origin <原远端 URL>
git fetch origin <分支>          # 建立 --force-with-lease 的比对基准
git push --force-with-lease origin <分支>
```

关键点：**必须先 fetch 再 force-with-lease**。刚 `remote add` 的仓库没有任何 remote-tracking ref，lease 无从比对，会失败。

## 预防

1. **filter-repo 之后立刻重配 remote 并 force push**，不要拖延——时间越久，新提交越多，越难看出是「重写」而非「真分叉」。
2. 更根本的：**别让 secret / 大文件进仓库**。`repowiki/conversations/` 含原始转录且未被 `.gitignore` 忽略，提交前必须扫描（见同批笔记）。
3. filter-repo 是**全历史重写**，成本固定。**一次跑就应该把所有该清的东西一起清掉**（密钥 + 大文件 + 误提交的二进制），避免为不同目的反复重写、反复让所有协作者重建副本。

## 适用范围

本地做过 `git filter-repo` 后、任何试图 push（或「找不到 origin」）的场景。

## git filter-repo --force 重写历史会吞掉未提交改动并 gc 掉可恢复对象，动手前必须先 stash

> 合并自蒸馏候选：git filter-repo --force 重写历史会吞掉未提交改动并 gc 掉可恢复对象，动手前必须先 stash

## filter-repo 的第三个副作用：吞掉未提交改动且无法恢复

同批事故中还发现：filter-repo 重写完成后自动 `reset --hard` 并执行 `repack + clean unreachable objects`，会话开始时三处**未提交**改动（AGENTS.md 精简、`codewiki/mcp/prompts.py` 的 `_TASK_MEMORY_AGENTS_SECTION` 常量精简、cli plan 文档三个章节）被一并吞掉。事后用 `git fsck --unreachable --no-reflogs` 找 dangling blob 抢救失败——收尾 gc 已把恢复通道消灭。

**预防**：重写历史前必须先清空工作区（commit 或 stash），重要未提交内容额外复制到 git 之外的临时位置，只对干净工作树执行 `--force`。部分丢失内容可从「会话系统提示注入的常量原文」「本会话读过的文件全文」手工恢复，但从未读过正文的段落无法恢复。
