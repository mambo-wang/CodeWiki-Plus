# Contributing

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/) (or `pip`).

```bash
git clone https://github.com/mambo-wang/CodeWiki-Plus.git
cd CodeWiki-Plus
uv sync --frozen          # or `pip install -e .[dev]`
uv run pre-commit install # enables ruff check + format on commit
uv run pytest -q          # verify setup
```
