---
type: lesson
title: "新增 submit 校验时先修测试素材 fixture 再断言规则优先级"
tags: ["lesson"]
metadata:
  date: 2026-11-26
  confidence_level: weak
  task_id: 他山之石
  source_session: "42b9be13-a446-8a36-9c69-8cd63018803e"
  related_modules: ["tests", "MCP_Tools_NoteLifecycle", "MCP_Tools_SkillCreator"]
  severity: medium
  source_ref: "conversations/conv-https-mp.weixin.qq.com-s-2IUREDltOXzXECO7tWIoPA-阅读文章看看有值得借鉴的-770c00.md"
  scene: "提交校验回归测试"
status: draft
author: iamwangbao-163-com
generated: { by: codewiki/5.16.7, at: 2026-11-25T23:04:19Z }
stale_after: 2027-05-25
origin: conversation

---

## Background

给 `consolidate_notes` 的 `source_notes` 和 `skill_creator` 的 `source_refs` 增加目标存在性校验后，原有测试 fixture 仍指向不存在的 `notes/some-note.md` 或 `notes/n.md`，导致新校验先失败，遮蔽了测试本来要验证的规则。

具体表现：

- `test_submit_validation_rule_names` 的本意是断言敏感内容、命名冲突、目标不存在等规则名，但默认素材先被新的存在性校验拦截。
- `test_submit_rejects_multiple_created_in_one_batch` 的本意是断言 `batch_fragmentation`，却先因 `notes/n.md` 不存在失败。
- `test_skill_match._mk_skill_repo` 没创建 `notes/some.md`，两个 submit 用例被新校验打破。

这是 `notes/2026-11-14-溯源背撑现状skill-lint-管技能素材consolidated-into-无人管两个-submit-不校验源目标.md` 所记落地变更之后的回归教训，与落地前架构事实互补。

## 正确做法

1. 在 fixture 中创建真实素材笔记，或把引用改为已存在的目标。
2. 让每个测试只违反它要断言的那条规则，避免前序校验遮蔽目标断言。
3. 修改校验顺序或新增校验时，先跑对应聚焦测试，再更新断言。

## Rationale

校验链是有优先级的；fixture 不合法会让测试名看似覆盖某规则，实际只验证了更早的前置条件，回归结果会误导后续维护。
