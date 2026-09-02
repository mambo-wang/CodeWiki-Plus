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

**possibly_stale** — 对端新鲜度标注（by_file 时间线）：目标源文件的最后一次
git 提交晚于笔记日期（留 1 天缓冲吸收当天提交噪声）即为 true；判据不可得
（文件未跟踪、git 不可用、笔记无日期）时返回 null——"不知道"不是失败，不猜。
与 `stale_after`（笔记自身年龄轴）互补不替换：一个管"知识描述的对象变没变"，
一个管"知识多大了"。_Avoid_: mtime 判定（clone 场景全量假阳性，已否决）。

**file knowledge** — 文件维度的知识检索（`by_file`）：回答"改这个文件之前，
这里有哪些历史知识"。按路径段映射笔记的 related_modules/related_components，
输出只含标题、成本、状态的时间线，不含正文（渐进式披露第一层）。预检性质，
不进 usage heat 信号。

**frontmatter module** — `codewiki/src/frontmatter.py`：repowiki 页面 frontmatter
的读取方（`parse_frontmatter`，readers accept the union of all legacy formats）
与 OKF 注入/私有元数据折叠（`inject_okf_frontmatter` / `fold_private_metadata`）。
该模块**只有读路径**——序列化 writer（render/update）与 `parse(render(x)) == x`
往返不变量尚无实现，是 P1-2 `files` 字段落地的前置项；页面类型路由
（`PAGE_TYPE_DIRS`）在 `codewiki/src/config.py`，不属于本模块。Slugify /
文件名约定同样不属于。永久接口约束：`capture_conversation` 输出（`conv-*.md`）
的 `status` 和 `task_id` 必须保持顶层单行键——stdlib-only hook
`.codebuddy/hooks/task_session_start.py` 逐行扫描它们且无法 import 本模块。

## Key decisions

- [ADR-0001 — 任务记忆保持 Markdown，不迁移 JSONL](adr/0001-task-memory-stays-markdown.md)（2026-08-24）
- [ADR-0002 — 任务记忆直写落盘，不设确认闸门](adr/0002-task-memories-direct-write.md)（2026-08-24）
- [ADR-0003 — 对端新鲜度判据用 git 提交时间而非 mtime](adr/0003-possibly-stale-uses-git-commit-time.md)（2026-09-02）
