"""MCP tools: init_workspace / add_workspace_repo — multi-repo harness scaffolding.

A "harness workspace" is a repo that hosts business repos as independent git
clones in subdirectories (excluded via .gitignore, not submodules) and only
carries product-level knowledge: workspace conventions, product repowiki and
the repo-map navigation.

- ``init_workspace`` turns an existing empty directory into such a workspace:
  bootstrap clone scripts, .gitignore, repo-map skeleton, workspace
  conventions section in AGENTS.md, and the standard product-level repowiki
  (reusing ``init_wiki``'s directory/template logic).

- ``add_workspace_repo`` registers one more business repo, transactionally
  updating four files: bootstrap.sh table, bootstrap.ps1 table, .gitignore
  and repo-map.md — then clones the repo by default.

Registration tables in the bootstrap scripts are the single source of truth;
entries are located by natural syntax anchors (``declare -A repos=(`` /
``$repos = [ordered]@{``) so hand-built workspaces can be adopted as-is.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "workspace"

# Syntax anchors for the registration tables inside bootstrap scripts.
# Templates and hand-built workspaces share these exact skeleton lines —
# do not change them without updating both the templates and these regexes.
_SH_TABLE_RE = re.compile(r"(?ms)^(declare -A repos=\(\n)(.*?)(^\)[ \t]*$)")
_PS_TABLE_RE = re.compile(r"(?ms)^(\$repos = \[ordered\]@\{\n)(.*?)(^\}[ \t]*$)")

_SH_ENTRY_LINE_RE = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*"([^"]*)"')
_PS_ENTRY_LINE_RE = re.compile(r'^\s*"([^"]+)"\s*=\s*"([^"]*)"')

# Directory names double as shell/PowerShell table keys and gitignore
# patterns — restrict to characters that need no quoting anywhere.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

_REPO_MAP_NEW_REPO_COMMENT = "<!-- 新增业务仓模板："


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _err(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _read_text(path: Path) -> str:
    # Normalize CRLF so the table regexes (anchored on \n) work everywhere.
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _render_template(name: str, **variables: str) -> str:
    text = (_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if leftover:
        raise ValueError(f"template {name} has unsubstituted placeholders: {leftover}")
    return text


def _validate_repo_args(workspace_p: Path, name: str, url: str) -> str | None:
    """Return an error message, or None when the repo entry is acceptable."""
    if not workspace_p.exists():
        return f"workspace_path does not exist: {workspace_p}"
    if not workspace_p.is_dir():
        return f"workspace_path is not a directory: {workspace_p}"
    if not name or not _NAME_RE.match(name) or name in (".", ".."):
        return f"illegal repo directory name {name!r}: only letters, digits, '.', '_' and '-' are allowed"
    if not url or '"' in url or "\n" in url:
        return f"illegal repo url {url!r}: must be non-empty and free of quotes/newlines"
    return None


# ---------------------------------------------------------------------------
# Bootstrap script table editing
# ---------------------------------------------------------------------------


def _parse_entries(body: str, is_sh: bool) -> dict:
    line_re = _SH_ENTRY_LINE_RE if is_sh else _PS_ENTRY_LINE_RE
    entries: dict = {}
    for line in body.splitlines():
        m = line_re.match(line)
        if m:
            entries[m.group(1)] = m.group(2)
    return entries


def _load_tables(workspace_p: Path) -> tuple[dict | None, str | None]:
    """Parse both bootstrap registration tables.  Returns (info, error)."""
    sh_path = workspace_p / "bootstrap.sh"
    ps_path = workspace_p / "bootstrap.ps1"
    missing = [p.name for p in (sh_path, ps_path) if not p.exists()]
    if missing:
        return None, (
            f"workspace appears uninitialized ({', '.join(missing)} missing). "
            f"Run init_workspace first. workspace={workspace_p}"
        )
    sh_text = _read_text(sh_path)
    ps_text = _read_text(ps_path)
    sh_m = _SH_TABLE_RE.search(sh_text)
    if not sh_m:
        return None, (
            "cannot locate the registration table in bootstrap.sh — expected a "
            "`declare -A repos=( ... )` block. Restore the skeleton lines or "
            "re-run init_workspace in a fresh directory."
        )
    ps_m = _PS_TABLE_RE.search(ps_text)
    if not ps_m:
        return None, (
            "cannot locate the registration table in bootstrap.ps1 — expected a "
            "`$repos = [ordered]@{ ... }` block. Restore the skeleton lines or "
            "re-run init_workspace in a fresh directory."
        )
    return (
        {
            "sh_path": sh_path,
            "ps_path": ps_path,
            "sh_text": sh_text,
            "ps_text": ps_text,
            "sh_entries": _parse_entries(sh_m.group(2), True),
            "ps_entries": _parse_entries(ps_m.group(2), False),
        },
        None,
    )


def _check_conflicts(info: dict, repos: list[tuple[str, str]]) -> str | None:
    """Hard-error when a directory name is registered with a different URL."""
    for name, url in repos:
        for source, entries in (
            ("bootstrap.sh", info["sh_entries"]),
            ("bootstrap.ps1", info["ps_entries"]),
        ):
            existing = entries.get(name)
            if existing is not None and existing != url:
                return (
                    f"directory name {name!r} is already registered in {source} with a "
                    f"different URL ({existing}). Not overwriting automatically — "
                    "reconcile the entry manually."
                )
    return None


def _insert_entry(text: str, table_re: re.Pattern, entry_line: str) -> str:
    m = table_re.search(text)
    head, body, tail = m.group(1), m.group(2), m.group(3)
    if body and not body.endswith("\n"):
        body += "\n"
    return text[: m.start()] + head + body + entry_line + "\n" + tail + text[m.end() :]


def _apply_registration(info: dict, repos: list[tuple[str, str]]) -> dict:
    """Insert every missing entry into both bootstrap scripts.

    Callers must have run ``_check_conflicts`` first.  Returns per-script
    action lists: each repo maps to ``registered`` or ``already_registered``.
    """
    sh_actions: dict = {}
    ps_actions: dict = {}
    sh_text, ps_text = info["sh_text"], info["ps_text"]
    for name, url in repos:
        if info["sh_entries"].get(name) == url:
            sh_actions[name] = "already_registered"
        else:
            sh_text = _insert_entry(sh_text, _SH_TABLE_RE, f'    ["{name}"]="{url}"')
            sh_actions[name] = "registered"
        if info["ps_entries"].get(name) == url:
            ps_actions[name] = "already_registered"
        else:
            ps_text = _insert_entry(ps_text, _PS_TABLE_RE, f'    "{name}" = "{url}"')
            ps_actions[name] = "registered"
    if any(a == "registered" for a in sh_actions.values()):
        _write_text(info["sh_path"], sh_text)
    if any(a == "registered" for a in ps_actions.values()):
        _write_text(info["ps_path"], ps_text)
    return {"bootstrap_sh": sh_actions, "bootstrap_ps1": ps_actions}


# ---------------------------------------------------------------------------
# .gitignore / repo-map editing
# ---------------------------------------------------------------------------


def _ensure_gitignore(workspace_p: Path, repo_names: list[str]) -> dict:
    path = workspace_p / ".gitignore"
    needed = [f"/{n}/" for n in repo_names]
    if not path.exists():
        repo_lines = "\n".join(f"/{n}/" for n in repo_names)
        _write_text(path, _render_template("gitignore.tpl", REPO_IGNORE_LINES=repo_lines))
        return {"status": "created", "added": needed}
    text = _read_text(path)
    existing = {line.strip() for line in text.splitlines()}
    missing = [line for line in needed if line not in existing]
    if missing:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(missing) + "\n"
        _write_text(path, text)
    return {"status": "updated" if missing else "up_to_date", "added": missing}


def _nav_row(name: str) -> str:
    return f"| {name} | `{name}/` | <!-- TODO: 填写职责 --> | `{name}/repowiki` | <!-- TODO --> |"


def _repo_map_section(name: str) -> str:
    return (
        f"## {name}（`{name}/`）\n"
        "\n"
        "**业务概述**\n"
        "\n"
        "<!-- TODO: 补充业务概述 -->\n"
        "\n"
        "**检索方式**\n"
        "\n"
        "```\n"
        f"query_wiki(query=<问题>, output_dir=<harness根>/{name}/repowiki)\n"
        "```\n"
    )


def _ensure_repo_map_entry(text: str, name: str) -> tuple[str, dict]:
    """Add the nav-table row and detail section for one repo to repo-map text."""
    result = {"nav_row": "skipped", "section": "skipped"}
    dir_cell = f"`{name}/`"
    lines = text.split("\n")

    row_exists = any(line.startswith("|") and dir_cell in line for line in lines)
    section_exists = any(line.startswith("## ") and dir_cell in line for line in lines)

    if not row_exists:
        insert_at = None
        for i, line in enumerate(lines):
            stripped = line.replace("|", "").strip()
            if line.startswith("|") and stripped and set(stripped) <= set("-:"):
                insert_at = i + 1
                break
        if insert_at is not None:
            lines.insert(insert_at, _nav_row(name))
            result["nav_row"] = "added"
        else:
            result["nav_row"] = "warning: navigation table not found; section only"

    if not section_exists:
        text = "\n".join(lines)
        section = _repo_map_section(name)
        idx = text.find(_REPO_MAP_NEW_REPO_COMMENT)
        if idx != -1:
            text = text[:idx] + section + "\n" + text[idx:]
        else:
            if not text.endswith("\n"):
                text += "\n"
            text = text + "\n" + section
        result["section"] = "added"
    else:
        text = "\n".join(lines)

    return text, result


# ---------------------------------------------------------------------------
# Cloning
# ---------------------------------------------------------------------------


def _clone_repo(workspace_p: Path, name: str, url: str, timeout: int) -> dict:
    dest = workspace_p / name
    if (dest / ".git").exists():
        return {"status": "skipped", "detail": "already cloned"}
    if dest.exists():
        return {
            "status": "warn",
            "detail": f"directory {dest} exists but is not a git repository; check manually",
        }
    try:
        proc = subprocess.run(
            ["git", "clone", url, str(dest)],
            cwd=str(workspace_p),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"status": "error", "detail": "git executable not found in PATH"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": f"git clone timed out after {timeout}s"}
    if proc.returncode == 0:
        return {"status": "ok", "detail": f"cloned into {dest}"}
    stderr_tail = (proc.stderr or proc.stdout or "").strip()[-500:]
    return {"status": "error", "detail": stderr_tail}


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


def handle_init_workspace(arguments: dict) -> str:
    """Initialize a multi-repo harness workspace.

    Parameters (from arguments dict):
        workspace_path: Existing directory to become the workspace root
            (default: current working directory).
        output_dir: Product-level repowiki directory (default: <workspace>/repowiki).
        refresh_conventions: Force-refresh the AGENTS.md conventions block
            (default: false — existing block is kept).
        with_readme: Create a README.md skeleton when missing (default: true).

    Repo registration and cloning are handled by add_workspace_repo; this tool
    only scaffolds the workspace skeleton with empty registration tables.
    """
    workspace_path = (arguments.get("workspace_path") or "").strip()
    if not workspace_path:
        workspace_path = os.getcwd()
    workspace_p = Path(workspace_path).resolve()
    if not workspace_p.exists():
        return _err(f"workspace_path does not exist: {workspace_p}")
    if not workspace_p.is_dir():
        return _err(f"workspace_path is not a directory: {workspace_p}")

    name = workspace_p.name
    output_dir = (arguments.get("output_dir") or "").strip()
    if not output_dir:
        output_dir_p = workspace_p / "repowiki"
    elif os.path.isabs(output_dir):
        output_dir_p = Path(output_dir).resolve()
    else:
        output_dir_p = (workspace_p / output_dir).resolve()

    refresh_conventions = bool(arguments.get("refresh_conventions", False))
    with_readme = bool(arguments.get("with_readme", True))

    results: dict = {
        "workspace_path": str(workspace_p),
        "name": name,
        "output_dir": str(output_dir_p),
    }
    warnings: list[str] = []

    # ── Bootstrap scripts (empty registration table; add via add_workspace_repo) ──
    sh_path = workspace_p / "bootstrap.sh"
    ps_path = workspace_p / "bootstrap.ps1"
    sh_exists, ps_exists = sh_path.exists(), ps_path.exists()
    if sh_exists != ps_exists:
        return _err(
            f"only one bootstrap script exists ({sh_path.name if sh_exists else ps_path.name}); "
            "remove the stray file or restore its pair, then re-run"
        )
    if not sh_exists:
        _write_text(sh_path, _render_template("bootstrap.sh.tpl", REPO_TABLE_SH=""))
        _write_text(ps_path, _render_template("bootstrap.ps1.tpl", REPO_TABLE_PS=""))
        results["bootstrap_scripts"] = "created"
    else:
        info, err = _load_tables(workspace_p)
        if err:
            return _err(err)
        results["bootstrap_scripts"] = "kept (already present)"

    # ── .gitignore ───────────────────────────────────────────────────────
    results["gitignore"] = _ensure_gitignore(workspace_p, [])

    # ── repo-map.md (user content wins once it exists) ───────────────────
    repo_map_path = output_dir_p / "wiki" / "repo-map.md"
    if repo_map_path.exists():
        results["repo_map"] = f"kept (already present): {repo_map_path}"
    else:
        repo_map_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(
            repo_map_path,
            _render_template(
                "repo-map.md.tpl",
                DATE=datetime.date.today().isoformat(),
                NAV_TABLE_ROWS="",
                REPO_SECTIONS="<!-- 尚无登记的业务仓：用 add_workspace_repo(url=<克隆URL>) 添加 -->",
            ),
        )
        results["repo_map"] = str(repo_map_path)

    # ── README skeleton ──────────────────────────────────────────────────
    readme_path = workspace_p / "README.md"
    if with_readme and not readme_path.exists():
        _write_text(readme_path, _render_template("readme.md.tpl", WORKSPACE_NAME=name))
        results["readme"] = str(readme_path)
    else:
        results["readme"] = "kept" if readme_path.exists() else "skipped"

    # ── Product-level repowiki + AGENTS.md ───────────────────────────────
    from codewiki.mcp.tools.init_wiki import initialize_wiki_tree

    tree = initialize_wiki_tree(workspace_p, output_dir_p, overwrite_schema=False)
    results["repowiki_tree"] = tree

    from codewiki.mcp.tools.agents_md import write_agents_md, write_workspace_conventions

    # Conventions block first so it reads before the CodeWiki usage block.
    results["agents_md_conventions"] = write_workspace_conventions(
        workspace_path=str(workspace_p), workspace_name=name, refresh=refresh_conventions
    )
    try:
        write_agents_md(repo_path=str(workspace_p), output_dir=str(output_dir_p), module_tree=None)
        results["agents_md_codewiki_block"] = str(workspace_p / "AGENTS.md")
    except Exception as e:  # must not block workspace scaffolding
        results["agents_md_codewiki_block"] = f"WARNING: {e}"
        logger.warning("Failed to write CodeWiki block in workspace AGENTS.md: %s", e)

    results["warnings"] = warnings
    results["status"] = "ok"
    results["next_steps"] = (
        "Workspace initialized. Next: "
        "1) Register business repos with add_workspace_repo(url=<clone URL>); "
        "2) For each business repo run init_wiki / analyze_repo with "
        "output_dir=<workspace>/<repo>/repowiki to build its repo-level wiki; "
        "3) Run analyze_workspace(workspace_path=<workspace root>) for cross-repo analysis; "
        "4) On POSIX run: chmod +x bootstrap.sh"
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


def _derive_repo_name(url: str) -> str:
    """Derive the workspace directory name from a git clone URL.

    Uses the last path segment (e.g. ``.../org/repo.git`` → ``repo``),
    handling trailing slashes, ``.git`` suffixes and SSH-style URLs
    (``git@host:org/repo.git``).  The result must still pass ``_NAME_RE``.
    """
    u = url.strip().rstrip("/")
    if (
        ":" in u
        and "/" in u
        and not u.startswith(("http://", "https://", "file://", "ssh://", "git://"))
    ):
        u = u.rsplit(":", 1)[1]  # git@host:org/repo → org/repo
    base = u.rsplit("/", 1)[-1]
    if base.endswith(".git"):
        base = base[:-4]
    return base.strip()


def handle_add_workspace_repo(arguments: dict) -> str:
    """Register a business repo into an initialized workspace.

    The directory name is derived from the repository URL (last path
    segment, ``.git`` stripped).  Transactionally updates bootstrap.sh,
    bootstrap.ps1, .gitignore and repo-map.md, then clones the repo by
    default.  Registration is written first; a clone failure never rolls it
    back.

    Parameters (from arguments dict):
        workspace_path: Workspace root (default: cwd).
        url: Git clone URL (required).
        clone: Clone immediately after registration (default: true).
        clone_timeout: Seconds for the git clone (default: 600).
    """
    workspace_path = (arguments.get("workspace_path") or "").strip()
    url = (arguments.get("url") or "").strip()
    clone = bool(arguments.get("clone", True))
    try:
        clone_timeout = int(arguments.get("clone_timeout", 600))
    except (TypeError, ValueError):
        return _err("clone_timeout must be an integer (seconds)")

    if not workspace_path:
        workspace_path = os.getcwd()
    workspace_p = Path(workspace_path).resolve()

    name = _derive_repo_name(url)

    err = _validate_repo_args(workspace_p, name, url)
    if err:
        return _err(err)

    info, err = _load_tables(workspace_p)
    if err:
        return _err(err)
    conflict = _check_conflicts(info, [(name, url)])
    if conflict:
        return _err(conflict)

    # All preflight checks passed — write the four artifacts.
    actions = _apply_registration(info, [(name, url)])
    results: dict = {
        "workspace_path": str(workspace_p),
        "name": name,
        "url": url,
        "bootstrap_sh": actions["bootstrap_sh"][name],
        "bootstrap_ps1": actions["bootstrap_ps1"][name],
        "gitignore": _ensure_gitignore(workspace_p, [name]),
    }

    repo_map_path = workspace_p / "repowiki" / "wiki" / "repo-map.md"
    if repo_map_path.exists():
        text = _read_text(repo_map_path)
        new_text, rm_status = _ensure_repo_map_entry(text, name)
        if new_text != text:
            _write_text(repo_map_path, new_text)
        results["repo_map"] = rm_status
    else:
        results["repo_map"] = "skipped (repowiki/wiki/repo-map.md not found)"

    if clone:
        results["clone"] = _clone_repo(workspace_p, name, url, clone_timeout)
        if results["clone"]["status"] == "error":
            results["warnings"] = [
                "clone failed but registration is complete — run ./bootstrap.sh "
                "or re-invoke with clone=true after fixing network/credentials"
            ]

    results["status"] = "ok"
    results["next_steps"] = (
        f"Repo {name!r} registered. Next: run init_wiki / analyze_repo with "
        f"output_dir=<workspace>/{name}/repowiki, then fill its 业务概述 section in "
        "repowiki/wiki/repo-map.md. On POSIX run: chmod +x bootstrap.sh"
    )
    return json.dumps(results, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Removal primitives
# ---------------------------------------------------------------------------


def _remove_entry_from_table(
    text: str, table_re: re.Pattern, line_re: re.Pattern
) -> tuple[str, bool]:
    """Remove the first line matching ``line_re`` from the table body."""
    m = table_re.search(text)
    if not m:
        return text, False
    head, body, tail = m.group(1), m.group(2), m.group(3)
    removed = False
    kept: list[str] = []
    for ln in body.split("\n"):
        if not removed and line_re.match(ln):
            removed = True
        else:
            kept.append(ln)
    if not removed:
        return text, False
    return text[: m.start()] + head + "\n".join(kept) + tail + text[m.end() :], True


def _remove_gitignore_line(workspace_p: Path, name: str) -> dict:
    path = workspace_p / ".gitignore"
    if not path.exists():
        return {"status": "skipped", "detail": ".gitignore not found"}
    target = f"/{name}/"
    lines = _read_text(path).split("\n")
    kept = [ln for ln in lines if ln.strip() != target]
    if len(kept) != len(lines):
        _write_text(path, "\n".join(kept))
        return {"status": "removed"}
    return {"status": "not_found"}


def _remove_repo_map_entry(text: str, name: str) -> tuple[str, dict]:
    """Remove the nav-table row and detail section for one repo from repo-map text."""
    result = {"nav_row": "not_found", "section": "not_found"}
    dir_cell = f"`{name}/`"
    lines = text.split("\n")

    kept = [ln for ln in lines if not (ln.startswith("|") and dir_cell in ln)]
    result["nav_row"] = "removed" if len(kept) != len(lines) else "not_found"
    lines = kept

    heading = f"## {name}（`{name}/`）"
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith(heading):
            start = i
            break
    if start is not None:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("## ") or lines[j].startswith(_REPO_MAP_NEW_REPO_COMMENT):
                end = j
                break
        del lines[start:end]
        result["section"] = "removed"

    new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return new_text, result


def handle_remove_workspace_repo(arguments: dict) -> str:
    """Deregister a business repo from an initialized workspace.

    Removes the entry from bootstrap.sh / bootstrap.ps1, the ``/<name>/``
    line from .gitignore and the nav row + section from repo-map.md.
    The cloned directory is kept unless ``delete_dir=true`` (irreversible).

    Parameters (from arguments dict):
        workspace_path: Workspace root (default: cwd).
        name: Registered subdirectory name of the business repo (required).
        delete_dir: Also delete the cloned directory (default: false).
    """
    workspace_path = (arguments.get("workspace_path") or "").strip()
    name = (arguments.get("name") or "").strip()
    delete_dir = bool(arguments.get("delete_dir", False))

    if not workspace_path:
        workspace_path = os.getcwd()
    workspace_p = Path(workspace_path).resolve()

    if not workspace_p.exists():
        return _err(f"workspace_path does not exist: {workspace_p}")
    if not workspace_p.is_dir():
        return _err(f"workspace_path is not a directory: {workspace_p}")
    if not name or not _NAME_RE.match(name) or name in (".", ".."):
        return _err(
            f"illegal repo directory name {name!r}: only letters, digits, '.', '_' and '-' are allowed"
        )

    info, err = _load_tables(workspace_p)
    if err:
        return _err(err)
    if name not in info["sh_entries"] and name not in info["ps_entries"]:
        return _err(f"repo {name!r} is not registered in this workspace; nothing to remove")

    results: dict = {"workspace_path": str(workspace_p), "name": name}

    sh_line = re.compile(rf'^\s*\["{re.escape(name)}"\]\s*=\s*"[^"]*"\s*$')
    ps_line = re.compile(rf'^\s*"{re.escape(name)}"\s*=\s*"[^"]*"\s*$')

    sh_text, sh_removed = _remove_entry_from_table(info["sh_text"], _SH_TABLE_RE, sh_line)
    if sh_removed:
        _write_text(info["sh_path"], sh_text)
    ps_text, ps_removed = _remove_entry_from_table(info["ps_text"], _PS_TABLE_RE, ps_line)
    if ps_removed:
        _write_text(info["ps_path"], ps_text)
    results["bootstrap_sh"] = "removed" if sh_removed else "not_found"
    results["bootstrap_ps1"] = "removed" if ps_removed else "not_found"

    results["gitignore"] = _remove_gitignore_line(workspace_p, name)

    repo_map_path = workspace_p / "repowiki" / "wiki" / "repo-map.md"
    if repo_map_path.exists():
        text = _read_text(repo_map_path)
        new_text, rm_status = _remove_repo_map_entry(text, name)
        if new_text != text:
            _write_text(repo_map_path, new_text)
        results["repo_map"] = rm_status
    else:
        results["repo_map"] = "skipped (repowiki/wiki/repo-map.md not found)"

    # Directory deletion happens after the registration is safely gone.
    dest = workspace_p / name
    if delete_dir:
        if dest.exists():
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
                results["directory"] = "deleted"
            else:
                results["directory"] = "skipped (not a plain directory)"
        else:
            results["directory"] = "not present"
    else:
        results["directory"] = (
            "kept (delete_dir=false; the directory is no longer gitignored — "
            "remove it manually or keep it out of the harness git)"
            if dest.exists()
            else "not present"
        )

    dir_action = {
        "deleted": "deleted.",
        "skipped (not a plain directory)": "not deleted (not a plain directory).",
        "not present": "was not present.",
        "kept (delete_dir=false; the directory is no longer gitignored — "
        "remove it manually or keep it out of the harness git)": "kept — delete manually if no longer needed.",
    }[results["directory"]]

    results["status"] = "ok"
    results["next_steps"] = (
        f"Repo {name!r} deregistered. The local clone at <workspace>/{name} was {dir_action} "
        "Verify with git status that the harness repo stays clean."
    )
    return json.dumps(results, ensure_ascii=False, indent=2)
