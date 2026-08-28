"""Multi-IDE hook wrappers shipped with codewiki.

This subpackage holds the *source* copies of hook scripts that the
``team-memory-hook`` MCP prompt / ``codewiki install-hooks`` CLI copy
into a user's project when they enable team-memory capture.
The wiring supports CodeBuddy (``<repo>/.codebuddy/hooks/``), Qoder
(``<repo>/.qoder/hooks/``) and Claude Code (``<repo>/.claude/hooks/``) —
``codewiki install-hooks`` auto-detects which IDE config dirs exist in
the repo root and wires each one found. The scripts are not invoked from
inside this package — only the copied files in the target project are run
by the IDE.
"""
