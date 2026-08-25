# CONTEXT.md

> Domain glossary and key decisions for this repo. Created by the engineering skills setup.
> Populate this lazily as terms get resolved — see `docs/agents/domain.md` and the
> `/domain-modeling` skill. You don't need to fill it in upfront.

## Glossary

**task memory** — 任务作用域的进度知识（本次做了什么、下一步、待办），累积于该任务的
memories，生命周期挂在任务上：一条任务记忆无论多老都只对该任务有意义，不按"年龄"晋升
为全局知识。与 Wiki 笔记（跨任务的通用经验，全局作用域）分轨互补。蒸馏直写落盘，不经
确认闸门（ADR-0002）；笔记的闸门保留。

**memory compaction** — 记忆巩固操作：把任务记忆中的旧条目有损压缩为文件头部摘要段，
并保留最近条目全文。产出直写不走确认闸门——它是可逆操作（原文全在 memory archive，
摘要不合格重跑一次即可），不属于"噪声知识进库"的闸门防御范围。

**memory archive** — 被压缩条目的原文存放地（memories-archive.md，append-only）。永不
进入任何自动加载路径，仅供人查证或压缩返工时回溯。

**review axes** — review_changes 代码审查的四类评审依据的规范短名，focus 枚举、上下文包
evidence 键、报告 axis 字段三处统一使用：`spec`（SPEC/设计文档）、`convention`（项目
Wiki 规范 + Doctrine）、`module_knowledge`（模块历史笔记）、`general`（内置通用
checklist）。评审对象 = 同一次 git 变更（since 或未提交），工具只做确定性收集与落盘，
推理外置给调用方 Agent（Doctrine 约束）。

**frontmatter module** — the deep module at `codewiki/src/frontmatter.py` that owns
repowiki page frontmatter read/write (`parse_frontmatter` / `render_frontmatter` /
`update`) and page-type routing (`route_page_type`, backed by `PAGE_TYPE_DIRS`).
Writer output is byte-compatible with the historical format; readers accept the union
of all legacy formats; `parse(render(x)) == x` is the round-trip invariant. Rollout:
readers first, then writers. Slugify / filename conventions are explicitly NOT part
of it. Permanent interface constraint: `capture_conversation` output (`conv-*.md`)
must keep `status` and `task_id` as top-level single-line keys — the stdlib-only hook
`.codebuddy/hooks/task_session_start.py` line-scans for them and cannot import this
module.

## Key decisions

- [ADR-0001 — 任务记忆保持 Markdown，不迁移 JSONL](adr/0001-task-memory-stays-markdown.md)（2026-08-24）
- [ADR-0002 — 任务记忆直写落盘，不设确认闸门](adr/0002-task-memories-direct-write.md)（2026-08-24）
