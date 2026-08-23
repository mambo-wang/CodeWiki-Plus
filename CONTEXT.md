# CONTEXT.md

> Domain glossary and key decisions for this repo. Created by the engineering skills setup.
> Populate this lazily as terms get resolved — see `docs/agents/domain.md` and the
> `/domain-modeling` skill. You don't need to fill it in upfront.

## Glossary

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

_No ADRs yet. Record architectural decisions under `docs/adr/` (see `docs/agents/domain.md`)._
