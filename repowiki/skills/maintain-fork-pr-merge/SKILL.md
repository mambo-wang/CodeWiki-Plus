---
name: maintain-fork-pr-merge
description: 当合入 fork 来源的 PR 且 mergeStateStatus=CONFLICTING/DIRTY 时——先 git merge-tree 探测冲突清单，查 maintainer_can_modify，再在 worktree 隔离目录解冲突后 push fork 分支，勿因 CI 绿直接 merge
type: Skill
status: stable
generated:
  by: codewiki/5.6.1
  at: "2026-09-06T11:43:46Z"
stale_after: 2026-12-05
metadata:
  summary: fork PR 冲突时的维护者合入 SOP：merge-tree 探测 + worktree 隔离 + push fork
  source_refs: ["wiki/scenarios/发布与依赖治理方法.md", "notes/2026-08-26-fork-来源的-pr-与目标分支冲突时的维护者合入流程merge-tree-探测-worktree-push-fork.md"]
  revisions: ["at: \"2026-09-06T11:43:46Z\"", {"at": "2026-09-06T11:45:12Z", "reason": "试用反馈：适用条件补 DRAFT 态 caveat（flag_issue skill-ineffective）", "source": "skill_creator"}, {"at": "2026-09-06T11:46:06Z", "reason": "drift 验证轮", "source": "skill_creator"}, {"at": "2026-09-06T11:50:16Z", "reason": "移除 drift 验证临时段，恢复正式正文", "source": "skill_creator"}]
  reason: created from candidate materials
  source: skill_creator
  installed_at: "2026-09-06T11:50:20Z"
  installed_to: .codebuddy/skills/maintain-fork-pr-merge/
  installed_hash: "sha256:3aa4f3725ce83a7c9c83531a737828dd674039eb7734fbaf1fc5d23f15db670e"
---


## 工作场景

维护者合入外部贡献者从 fork 发起的 PR，且 PR 分支与目标分支存在冲突（mergeStateStatus=CONFLICTING/DIRTY）。本仓的典型情境：评审期间 develop 又合入了新提交，导致 fork PR 的改动与主线重叠。

## 适用条件

- PR 的 head 分支在贡献者 fork 仓库中（isCrossRepository=true），本地 `git fetch <pr-branch>` 会 404
- `gh pr view --json mergeable,mergeStateStatus` 显示 CONFLICTING 或 DIRTY
- 注意：此时 CI 检查可能是全绿——CI 通过不等于可合并，以 mergeStateStatus 为准
- mergeStateStatus=DRAFT（CI 未跑完）时先等结果再探测冲突，勿提前判定

## 核心 SOP

1. 探测冲突清单：`git merge-tree --write-tree --name-only <base> <head>`——无需真实 checkout/merge 即可拿到冲突文件列表
2. 确认可否代改：`gh pr view --json isCrossRepository,headRepository`；fork PR 合入前查 `gh api repos/<owner>/<repo>/pulls/<n> --jq .maintainer_can_modify`——为 false 时只能请作者解决或换合并策略
3. 隔离解冲突：工作区有未提交改动时，用 `git worktree add <tmp> <head> -b <branch>` 在独立目录解决冲突，不污染主工作区
4. 更新 PR 分支：冲突解决后 `git push https://github.com/<fork-owner>/<repo>.git <local-branch>:<pr-branch>`（maintainer_can_modify=true 时 GitHub 允许维护者推 fork 的 PR head）
5. 收尾清理：`git worktree remove --force` + `git branch -D`，再 `gh pr merge --merge`

## 判断逻辑

- mergeStateStatus=DIRTY ≠ CI 失败：先看冲突字段，不要先怪 CI
- 主工作区是否常驻未提交改动决定是否必须走 worktree：常驻则必须隔离
- maintainer_can_modify 是代改的前提闸门：false 时一切 push fork 方案不可行

## 禁忌与反模式

- 不要直接在主工作区 checkout PR 分支解冲突（污染未提交改动）
- 不要因 CI 绿就点 merge（mergeStateStatus 会拒绝，但先探测可省一轮）
- 不要试图 fetch fork 的分支名到本地远程（不在主仓库，fetch 404 是预期行为）
- maintainer_can_modify=false 时不要尝试 push fork（无权限，会失败）

