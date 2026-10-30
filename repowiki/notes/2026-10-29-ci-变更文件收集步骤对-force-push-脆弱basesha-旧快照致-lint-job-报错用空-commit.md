---
type: pitfall
title: "CI 变更文件收集步骤对 force-push 脆弱——base.sha 旧快照致 Lint job 报错，用空 commit 重新触发"
tags: ["45", "pitfall"]
metadata:
  date: 2026-10-29
  confidence_level: weak
  task_id: 产品维护
  source_session: "23bfb17d128a4fecb57c58b6e7d89639"
  related_modules: ["github-ci"]
  severity: medium
  source_ref: "conversations/conv-我先查一下-CodeBuddy-hooks-官方文档确认-`SessionEnd`-的-`matcher`-正确取值，同.md"
  scene: "发版流程 / CI 排障"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.4, at: 2026-10-29T09:09:14Z }
stale_after: 2027-04-27
origin: conversation

---

## 现象

v5.16.5 发版的 PR #45 中，CI 的 Lint job 失败，但本地 `ruff format --check` 完全干净。失败步骤不是 lint 本身，而是前置的「Collect changed Python files」步骤报错。

## 根因

`.github/workflows/ci.yml` 的变更文件收集用 `git diff base...head`，base 取 `github.event.pull_request.base.sha`。force-push 重做 commit 后，该 sha 是 PR 事件里的旧快照，diff range 失效，导致收集步骤本身失败——与 lint 结果无关。

## 正确做法 / Recovery

- 重做已推送的 commit 时尽量避免 force-push，优先用新 commit 顶上去。
- 已 force-push 后的恢复路径（本次实证）：补一个空 commit 推送重新触发 CI——`git commit --allow-empty -m "ci: retrigger lint after force-push invalidated diff range"`，之后 CI 全绿、PR 正常合并。
- 排障口径：lint 失败但本地干净时，先区分「lint 真失败」与「diff 收集步骤失败」，不要盲目改格式。

## Rationale

该 workflow 对 force-push 的脆弱性在 v5.16.5 发版中实际踩中并实证了恢复路径；长期修复（改用 merge-base 或 push 事件口径）已记入待办，本笔记固化排障判据与即时恢复手段。
