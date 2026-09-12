# Contributing

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/) (or `pip`).

1. Fork https://github.com/mambo-wang/CodeWiki-Plus on GitHub, then:

```bash
git clone https://github.com/<YOUR_USERNAME>/CodeWiki-Plus.git
cd CodeWiki-Plus
git remote add upstream https://github.com/mambo-wang/CodeWiki-Plus.git
uv sync --frozen          # installs project dependencies
uv run pre-commit install # enables ruff check + format on commit
uv run pytest -q          # verify setup
```

2. Create a feature branch, push to your fork, and open a PR against `mambo-wang:develop`.

## Capability convention (tri-state gates)

任何会自动改变知识内容或生命周期的语义归并类新能力，必须实现为**三态门控**（tri-state gate，见 `CONTEXT.md` glossary）：

- `off` — 不采集、不生效；
- `observe` — 采集并记录「本应做什么」，但不改核心结果；
- `enforce` — 真正改变结果。

纪律：**新能力默认 `observe`**，用离线数据证明收益且无误伤后才升 `enforce`；不得为单个能力发明第四种状态，不得绕过 observe 直接 enforce。所有门控能力登记进 `docs/capability-matrix.md`，发布时更新。
