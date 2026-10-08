# Domain Docs

工程技能探索代码库时如何消费本仓库的领域文档。

## 探索前先读这些

- **`CONTEXT.md`**（仓库根）——本仓库术语表的**唯一事实源**。根目录同时存在 **`GLOSSARY.md`**，它是指向 `CONTEXT.md` 的符号链接，只为让按 `GLOSSARY.md` 取词的技能（`/tdd`、`/diagnosing-bugs`、`/pr`、`/triage`、`/domain-modeling`、上游改名前的 `CONTEXT.md` 口径）读到同一份内容。
- **`GLOSSARY-MAP.md`**：本仓库没有（单上下文）。若将来出现，它指向每个 context 各自的 `GLOSSARY.md`，按需读相关那份。
- **`docs/adr/`**：读与本次改动区域相关的 ADR。

这些文件都不存在时，**静默继续**。不要专门报告缺失，也不要上来就建议新建：`/domain-modeling`（由 `/grill-with-docs`、`/improve-codebase-architecture` 驱动）会在术语或决策真正确定时按需创建它们。

**写回规则**：新增/修改词条写 `CONTEXT.md`，不要写 `GLOSSARY.md`——原子保存的编辑器会把软链接替换成实体文件，从而出现两份互相漂移的术语表。

## 文件结构

单上下文（本仓库即此类，绝大多数仓库也是）：

```
/
├── CONTEXT.md          ← 术语表事实源
├── GLOSSARY.md         → CONTEXT.md（符号链接别名）
├── docs/adr/
│   ├── 0001-task-memory-stays-markdown.md
│   └── 0002-task-memories-direct-write.md
└── src/
```

多上下文仓库（根目录存在 `GLOSSARY-MAP.md` 时）：

```
/
├── GLOSSARY-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── GLOSSARY.md
    │   └── docs/adr/                  ← context 内决策
    └── billing/
        ├── GLOSSARY.md
        └── docs/adr/
```

## 用术语表里的词

输出里点到领域概念时（issue 标题、重构提案、假设、测试名），用 `CONTEXT.md` 给出的定义，不要滑回术语表明确不建议的同义词。

如果你需要的概念术语表里还没有，那本身是个信号：要么你在发明项目并不使用的说法（重新想想），要么确实存在空白（记给 `/domain-modeling`）。

## 标记 ADR 冲突

输出与既有 ADR 冲突时，显式说出来，而不是静默覆盖：

> _与 ADR-0007（conflict case 页型）冲突，但值得重开，因为……_
