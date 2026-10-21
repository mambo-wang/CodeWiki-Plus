---
name: codewiki-setup
description: "One-shot install or upgrade of CodeWiki plus full project wiring: pip-install codewiki-plus, then run codewiki setup (hooks + session capture + .mcp.json + skill files)"
disable-model-invocation: true
---

# codewiki-setup

Install or upgrade CodeWiki in one shot and wire the current project end to end (hooks + session capture, `.mcp.json`, skill files).

Run the two steps below in order; if either fails, stop and report the error to the user — do not continue.

## 1. Install/upgrade the package

```
pip install --upgrade codewiki-plus
```

If `pip` is unavailable, use `python -m pip install --upgrade codewiki-plus` instead.

## 2. Wire the project

Run in the current project root:

```
codewiki setup
```

If the `codewiki` command is not on PATH (e.g. PATH has not been refreshed right after install), use `python -m codewiki setup` instead.

setup does three things in one pass: wires hooks and session capture for every detected host IDE, creates or merges `.mcp.json` (the codewiki MCP server) in the project root, and generates the `codewiki-*` skill files.

When done, run `/codewiki-init-wiki` to initialize the project wiki.

This skill is a manual entry point (disable-model-invocation: true): zero standing context, triggered only when the user explicitly invokes /codewiki-setup.
