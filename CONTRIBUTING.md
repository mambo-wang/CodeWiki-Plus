# Contributing

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/) (or `pip`).

1. Fork https://github.com/mambo-wang/CodeWiki-Plus on GitHub, then:

```bash
git clone https://github.com/<YOUR_USERNAME>/CodeWiki-Plus.git
cd CodeWiki-Plus
git remote add upstream https://github.com/mambo-wang/CodeWiki-Plus.git
uv sync --frozen          # or `pip install -e .[dev]`
uv run pre-commit install # enables ruff check + format on commit
uv run pytest -q          # verify setup
```

Create a feature branch, push to your fork, and open a PR against `mambo-wang:develop`.
