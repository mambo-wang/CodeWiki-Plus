from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import argparse
import os
import re

# Constants
OUTPUT_BASE_DIR = "output"
DEPENDENCY_GRAPHS_DIR = "dependency_graphs"
DOCS_DIR = "docs"
META_DIR = ".meta"
FIRST_MODULE_TREE_FILENAME = "first_module_tree.json"
MODULE_TREE_FILENAME = "module_tree.json"
OVERVIEW_FILENAME = "overview.md"
# LLM Wiki constants
SCHEMA_FILENAME = "schema.yaml"
NOTES_DIR = "notes"
INDEX_FILENAME = "index.md"
LOG_FILENAME = "log.md"
# Team-layout Phase 1 (D5): append_log writes monthly shards ``log-YYYY-MM.md``
# (pure-append, git-merge friendly) instead of rewriting a single log.md.
# The legacy log.md stays on disk read-only for compatibility.
LOG_SHARD_PREFIX = "log-"
SEARCH_INDEX_FILENAME = "search_index.db"
SYMBOL_MAP_FILENAME = "symbol_map.json"
# LLM Wiki knowledge layer — structured layout constants
WIKI_DIR = "wiki"
RAW_DIR = "raw"
RAW_SOURCES_DIR = "raw/sources"
# L0 archive (team-memory fusion): distilled conversations are moved here for
# permanent provenance. Link-only layer — NOT indexed for BM25 search; reached
# by following note source_ref links (view_repo_file). raw/ stays the pending
# staging queue.
CONVERSATIONS_DIR = "conversations"
# Task memory layer — per-task knowledge store (task.md + memories.md + index)
TASKS_DIR = "tasks"
TASKS_INDEX_FILENAME = ".index.json"
TASKS_MEMORIES_FILENAME = "memories.md"
TASK_BINDINGS_DIR = "task_bindings"
# Retired (consumed) vouchers live in a subdirectory of TASK_BINDINGS_DIR. They
# keep session→task attribution alive after the live voucher is consumed, which
# the directory-scoped gitignore entry already covers.
CONSUMED_BINDINGS_DIR = "consumed"
SOURCE_REGISTRY_FILENAME = "source_registry.json"
ISSUES_FILENAME = "issues.json"
PROJECT_FILENAME = "project.json"
# Team-layout Phase 1 (D1: "git stores content, everything rebuildable stays
# local"): derived/index/runtime files that must NOT be committed.  Each has a
# self-heal rebuild path — directory scan (tasks/.index.json, source_registry),
# re-analysis (.meta/*.json), or rebuild_index (wiki/index.md).  Paths are
# relative to the wiki output_dir (repowiki root), posix separators.
TEAM_LAYOUT_REBUILDABLE_FILES = [
    "wiki/index.md",  # rebuild_index (ensure_index self-heal on read paths)
    ".meta/edit_history.json",  # undo semantics delegated to git history (D6)
    ".meta/metadata.json",
    ".meta/module_tree.json",
    ".meta/symbol_map.json",
    ".meta/project.json",
    ".meta/overview_refs.json",
    ".meta/aggregate_state.json",
    ".meta/source_registry.json",
    ".meta/job.json",  # ADR-0020 generation ledger — local progress state, rebuilt on next run
    ".meta/change_plan.json",  # ADR-0020 operator plan — rebuilt from tree+manifest+diff
    ".meta/user_id",  # repo-local identity pin (see resolve_user_id); machine-local
    ".meta/task_bindings/",  # session-scoped one-shot vouchers, no repo value
    ".meta/locks/",  # centralized cross-process lock files, machine-local runtime
    "tasks/.index.json",  # self-heals from tasks/*/task.md frontmatter scan
    "distill-jobs.json",  # local runtime state, restartable
]
# Mapping from page_type to subdirectory name under wiki/
PAGE_TYPE_DIRS = {
    "module": "modules",
    "entity": "entities",
    "concept": "concepts",
    "source": "sources",
    "comparison": "comparisons",
    "query": "queries",
    # P2 (team-memory fusion): L2 work-method scene blocks — consolidated
    # reusable knowledge (SOP / judgment logic / taboos / principles) distilled
    # from confirmed notes via consolidate_notes.
    "scenario": "scenarios",
}

# skill-creator (issue #24, ADR-0004): two-zone skill layout.
# Draft zone lives at the repowiki ROOT (sibling of notes/, not under wiki/ —
# skills are behaviour assets, not code-structure docs) and is managed:
# indexed (source="skill"), linted (skill_sections check), never IDE-effective.
# Effect zone lives at the REPO root, outside repowiki entirely: IDE-discovered
# and effective, never scanned by any repowiki tool. PAGE_TYPE_DIRS stays
# untouched because its values are wiki/-relative by convention; the skill
# page type routes through SKILLS_DIR via page_router + schema declaration.
SKILLS_DIR = "skills"  # draft zone, relative to output_dir (repowiki root)
SKILL_EFFECT_DIR = ".codebuddy/skills"  # effect zone, relative to repo root

# ADR-0007 (conflict first-class object): top-level conflicts/ directory —
# governance metadata (adjudication records), NOT knowledge. Same layout
# family as skills/: lives at the repowiki ROOT, never indexed into the
# search corpus, excluded from the generic lint audits; its health is owned
# by the dedicated open_conflicts lint check.
CONFLICTS_DIR = "conflicts"


# Files excluded from wiki index and search (system files).
# Team-layout Phase 1: membership also matches monthly log shards
# (``log-YYYY-MM.md``) so every scanner that filters via
# ``md.name in WIKI_SYSTEM_FILES`` keeps excluding them without per-site edits.
class _WikiSystemFiles(frozenset):
    """frozenset whose ``in`` also matches ``log-*.md`` shard names."""

    _LOG_SHARD_RE = re.compile(r"log-\d{4}-\d{2}\.md")

    def __contains__(self, name: object) -> bool:
        if isinstance(name, str) and self._LOG_SHARD_RE.fullmatch(name):
            return True
        return super().__contains__(name)


WIKI_SYSTEM_FILES = _WikiSystemFiles({"index.md", "log.md", "overview.md", "schema.yaml"})

# OKF v0.2 actor convention (§7): '<producer>/<version>' for agents and tools
# (e.g. ``reference_agent/gemini-2.5-pro``), 'human:<id>' for people,
# 'process:<id>' for pipelines.  Single source of truth for the actor string
# used in `generated.by` / `verified[].by` fields.
ACTOR_NAME = "codewiki"
OKF_VERSION = "0.2"


def actor_id() -> str:
    """Return the OKF actor id for this tool, e.g. ``codewiki/5.2.0`` (§7)."""
    from codewiki import __version__

    return f"{ACTOR_NAME}/{__version__}"


# --------------------------------------------------------------------------- #
# T2 identity (docs/团队知识库支持优化设计方案.md §4.1)
# --------------------------------------------------------------------------- #

# Per-user git identity: resolved per lookup dir and cached. The env override
# (CODEWIKI_USER) and the repo pin are checked live on every call so a
# pseudonym applies immediately and a re-pinned clone is picked up at once.
# Key '' means "this process' cwd" (no ``git -C`` prefix given).
_GIT_USER_NAME_CACHE: dict = {}
_GIT_USER_EMAIL_CACHE: dict = {}

# Filename-safe charset for the telemetry namespace: alphanumerics, dash,
# underscore. Everything else (spaces, CJK, dots...) collapses to a dash.
_USER_ID_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _git_config_value(key: str, lookup_dir: Optional[str] = None) -> str:
    """``git config <key>`` value ('' on failure).

    Resolution is *directory-anchored* when *lookup_dir* is given (``git -C``),
    so the same clone yields the same identity no matter which process asks —
    an IDE-spawned MCP server whose cwd is the editor's install dir otherwise
    resolves a different (or empty) config chain than a login shell. Without a
    dir we fall back to the process cwd, then the global config, as git does by
    default.
    """
    import subprocess

    cmd = (
        ["git", "config", key] if not lookup_dir else ["git", "-C", str(lookup_dir), "config", key]
    )
    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": 2,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        # Console-less parent (IDE-spawned MCP server): without this flag
        # every git child allocates a flashing console window.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, **kwargs)
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except Exception:
        pass
    return ""


def _git_user_name(lookup_dir: Optional[str] = None) -> str:
    """``git config user.name`` for *lookup_dir*; '' when unset/failing."""
    key = str(lookup_dir or "")
    if key not in _GIT_USER_NAME_CACHE:
        _GIT_USER_NAME_CACHE[key] = _git_config_value("user.name", key or None)
    return _GIT_USER_NAME_CACHE[key]


def _git_user_email(lookup_dir: Optional[str] = None) -> str:
    """``git config user.email`` for *lookup_dir*; '' when unset/failing.

    Preferred over user.name for namespacing: emails are effectively globally
    unique (user.name collisions across teammates are common).
    """
    key = str(lookup_dir or "")
    if key not in _GIT_USER_EMAIL_CACHE:
        _GIT_USER_EMAIL_CACHE[key] = _git_config_value("user.email", key or None)
    return _GIT_USER_EMAIL_CACHE[key]


def _login_name() -> str:
    """OS login name; '' when unavailable (services / some CI sandboxes)."""
    try:
        return os.getlogin() or ""
    except Exception:
        return ""


def _sanitize_user_id(raw: str) -> str:
    """Filename-safe form of *raw*: [A-Za-z0-9_-] only, truncated to 40 chars."""
    safe = _USER_ID_UNSAFE_RE.sub("-", (raw or "").strip()).strip("-")
    if not safe:
        return "local"
    return safe[:40]


_USER_ID_CACHE_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    ".codewiki_user_id",
)


def _read_user_id_cache() -> str:
    """Persisted user_id from a previous process, avoiding a ``git`` subprocess
    on every cold start. Empty string when absent/unreadable."""
    try:
        with open(_USER_ID_CACHE_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _write_user_id_cache(uid: str) -> None:
    """Best-effort persist; failure is non-fatal (next start re-derives)."""
    try:
        os.makedirs(os.path.dirname(_USER_ID_CACHE_PATH), exist_ok=True)
        with open(_USER_ID_CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(uid)
    except Exception:
        pass


# Repo-local identity pin: ``<output_dir>/.meta/user_id``. Gitignored, machine-local,
# rebuildable (same class as tasks/.index.json). It exists because every other input
# to this resolution is a FUNCTION OF THE PROCESS ENVIRONMENT: the %APPDATA%/HOME
# cache and ``git config`` (which needs HOME for ~/.gitconfig) are all unavailable in
# an IDE-spawned service-state MCP server, which then falls back to os.getlogin()
# and splits ONE person across two memory shards. The clone is the one artifact every
# channel (MCP / CLI / hook subprocess) certainly shares — so pin the identity to it.
_USER_ID_PIN_RELPATH = os.path.join(".meta", "user_id")


def _user_id_pin_path(output_dir) -> Optional[str]:
    if not output_dir:
        return None
    try:
        return os.path.join(str(output_dir), _USER_ID_PIN_RELPATH)
    except (TypeError, ValueError):
        return None


def _read_user_id_pin(output_dir) -> str:
    """Pinned uid for this clone; '' when absent/unreadable.

    Sanitized on read: the value becomes a filename component
    (``memories/<uid>.md``), so a hand-edited or foreign pin must not smuggle a
    path separator.
    """
    path = _user_id_pin_path(output_dir)
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip()
    except Exception:
        return ""
    return _sanitize_user_id(raw) if raw else ""


def _write_user_id_pin(output_dir, uid: str) -> None:
    """Best-effort pin; failure is non-fatal (identity still resolves this call)."""
    path = _user_id_pin_path(output_dir)
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(uid)
    except Exception:
        pass


def resolve_user_id(output_dir=None) -> tuple:
    """Return ``(uid, source)`` — the identity and which rung produced it.

    Priority: ``CODEWIKI_USER`` env (explicit pseudonym) > repo-local pin >
    ``git -C <output_dir> config user.email`` > the same ``user.name`` >
    machine cache (``%APPDATA%\\.codewiki_user_id``) > ``os.getlogin()`` > 'local'.
    ``source`` is one of ``env|pin|git-email|git-name|cache|login|local`` and is
    surfaced in tool responses so identity drift becomes visible instead of
    silently depositing extra shards.

    git ranks *above* the cache on purpose: the cache is a memoization of a past
    derivation, and a past derivation can be a degraded channel's login-name
    fallback. Trusting it over a readable git config would re-pin the clone on the
    wrong identity forever. The cache stays as the fallback for channels that
    cannot run git at all.

    Not an auth mechanism — a namespace. Only a git-verified resolution writes the
    pin, so the clone converges on the person identity and later channels inherit it
    even with a stripped environment. To change identity in a clone, delete
    ``<output_dir>/.meta/user_id``.
    """
    env = os.getenv("CODEWIKI_USER", "").strip()
    if env:
        return _sanitize_user_id(env), "env"
    pinned = _read_user_id_pin(output_dir)
    if pinned:
        return pinned, "pin"

    lookup_dir = str(output_dir) if output_dir else None
    email = _git_user_email(lookup_dir)
    if email:
        uid, source = _sanitize_user_id(email), "git-email"
    else:
        name = _git_user_name(lookup_dir)
        if name:
            uid, source = _sanitize_user_id(name), "git-name"
        else:
            # No git in this process (no HOME, no binary, non-repo dir): fall back
            # to whatever a previous healthy channel memoized, then the account.
            cached = _read_user_id_cache()
            if cached:
                uid, source = cached, "cache"
            else:
                login = _login_name()
                uid, source = (_sanitize_user_id(login), "login") if login else ("local", "local")

    # Only a git-verified identity is persisted. Everything below it on the chain is
    # a guess about the machine, not the person, and freezing a guess is how one
    # developer ends up with two memory shards.
    if source in ("git-email", "git-name"):
        _write_user_id_cache(uid)
        _write_user_id_pin(output_dir, uid)
    return uid, source


def user_id(output_dir=None) -> str:
    """Stable per-user identity for telemetry / task-memory namespacing.

    Thin wrapper over resolve_user_id() when the caller only needs the id; pass
    ``output_dir`` (the repowiki dir) so the repo-local pin applies. See
    resolve_user_id() for the full priority chain.
    """
    return resolve_user_id(output_dir)[0]


def meta_join(base_dir, filename):
    """Return ``base_dir/.meta/filename`` (for writing metadata files)."""
    return os.path.join(str(base_dir), META_DIR, filename)


def meta_resolve(base_dir, filename):
    """Return the path to a metadata file, checking ``.meta/`` first.

    Falls back to the legacy ``base_dir/filename`` location for
    backward compatibility with docs generated before the ``.meta/``
    directory was introduced.
    """
    new_path = os.path.join(str(base_dir), META_DIR, filename)
    if os.path.exists(new_path):
        return new_path
    old_path = os.path.join(str(base_dir), filename)
    if os.path.exists(old_path):
        return old_path
    return new_path  # default to new location


MAX_DEPTH = 3
# Default max token settings
DEFAULT_MAX_TOKENS = 32_768
DEFAULT_MAX_TOKEN_PER_MODULE = 36_369
DEFAULT_MAX_TOKEN_PER_LEAF_MODULE = 16_000
# Legacy constants (for backward compatibility)
MAX_TOKEN_PER_MODULE = DEFAULT_MAX_TOKEN_PER_MODULE
MAX_TOKEN_PER_LEAF_MODULE = DEFAULT_MAX_TOKEN_PER_LEAF_MODULE

# CLI context detection
_CLI_CONTEXT = False


def set_cli_context(enabled: bool = True):
    """Set whether we're running in CLI context (vs web app)."""
    global _CLI_CONTEXT
    _CLI_CONTEXT = enabled


def is_cli_context() -> bool:
    """Check if running in CLI context."""
    return _CLI_CONTEXT


# LLM services
# In CLI mode, these will be loaded from ~/.codewiki/config.json + keyring
# In web app mode, use environment variables
MAIN_MODEL = os.getenv("MAIN_MODEL", "claude-sonnet-4")
FALLBACK_MODEL_1 = os.getenv("FALLBACK_MODEL_1", "glm-4p5")
CLUSTER_MODEL = os.getenv("CLUSTER_MODEL", MAIN_MODEL)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://0.0.0.0:4000/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-1234")


@dataclass
class Config:
    """Configuration class for CodeWiki."""

    repo_path: str
    output_dir: str
    dependency_graph_dir: str
    docs_dir: str
    max_depth: int
    # LLM configuration
    llm_base_url: str
    llm_api_key: str
    main_model: str
    cluster_model: str
    fallback_model: str = FALLBACK_MODEL_1
    # Provider configuration
    provider: str = "openai-compatible"  # openai-compatible, anthropic, bedrock, azure-openai
    aws_region: str = "us-east-1"
    api_version: str = "2024-12-01-preview"  # Azure OpenAI API version
    azure_deployment: str = ""  # Azure OpenAI deployment name
    # Max token settings
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_token_per_module: int = DEFAULT_MAX_TOKEN_PER_MODULE
    max_token_per_leaf_module: int = DEFAULT_MAX_TOKEN_PER_LEAF_MODULE
    # Agent instructions for customization
    agent_instructions: Optional[Dict[str, Any]] = None

    @property
    def include_patterns(self) -> Optional[List[str]]:
        """Get file include patterns from agent instructions."""
        if self.agent_instructions:
            return self.agent_instructions.get("include_patterns")
        return None

    @property
    def exclude_patterns(self) -> Optional[List[str]]:
        """Get file exclude patterns from agent instructions."""
        if self.agent_instructions:
            return self.agent_instructions.get("exclude_patterns")
        return None

    @property
    def focus_modules(self) -> Optional[List[str]]:
        """Get focus modules from agent instructions."""
        if self.agent_instructions:
            return self.agent_instructions.get("focus_modules")
        return None

    @property
    def doc_type(self) -> Optional[str]:
        """Get documentation type from agent instructions."""
        if self.agent_instructions:
            return self.agent_instructions.get("doc_type")
        return None

    @property
    def custom_instructions(self) -> Optional[str]:
        """Get custom instructions from agent instructions."""
        if self.agent_instructions:
            return self.agent_instructions.get("custom_instructions")
        return None

    def get_prompt_addition(self) -> str:
        """Generate prompt additions based on agent instructions."""
        if not self.agent_instructions:
            return ""

        additions = []

        if self.doc_type:
            doc_type_instructions = {
                "api": "Focus on API documentation: endpoints, parameters, return types, and usage examples.",
                "architecture": "Focus on architecture documentation: system design, component relationships, and data flow.",
                "user-guide": "Focus on user guide documentation: how to use features, step-by-step tutorials.",
                "developer": "Focus on developer documentation: code structure, contribution guidelines, and implementation details.",
                "business": "Focus on business logic documentation: describe business workflows, processing pipelines, state transitions, and domain rules. Emphasize WHAT the system does for users and WHY, trace end-to-end business scenarios through the code, and document domain-specific terminology. De-emphasize infrastructure and deployment details.",
                "design": "Generate technical design documentation optimized for AI comprehension. For each module, describe in depth: (1) module responsibilities and boundaries, (2) detailed implementation logic and business rules, (3) data flow within and through the module, (4) interface contracts — inputs, outputs, and side effects, (5) internal layered design and component collaboration patterns, (6) relationships and dependencies with other modules, (7) constraints, assumptions, and edge cases. Use precise technical language. Include Mermaid diagrams for complex flows and interactions. Do not limit documentation length — let the content depth match the module's complexity.",
            }
            if self.doc_type.lower() in doc_type_instructions:
                additions.append(doc_type_instructions[self.doc_type.lower()])
            else:
                additions.append(f"Focus on generating {self.doc_type} documentation.")

        if self.focus_modules:
            additions.append(
                f"Pay special attention to and provide more detailed documentation for these modules: {', '.join(self.focus_modules)}"
            )

        if self.custom_instructions:
            additions.append(f"Additional instructions: {self.custom_instructions}")

        return "\n".join(additions) if additions else ""

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Config":
        """Create configuration from parsed arguments."""
        repo_name = os.path.basename(os.path.normpath(args.repo_path))
        sanitized_repo_name = "".join(c if c.isalnum() else "_" for c in repo_name)

        return cls(
            repo_path=args.repo_path,
            output_dir=OUTPUT_BASE_DIR,
            dependency_graph_dir=os.path.join(OUTPUT_BASE_DIR, DEPENDENCY_GRAPHS_DIR),
            docs_dir=os.path.join(OUTPUT_BASE_DIR, DOCS_DIR, f"{sanitized_repo_name}-docs"),
            max_depth=MAX_DEPTH,
            llm_base_url=LLM_BASE_URL,
            llm_api_key=LLM_API_KEY,
            main_model=MAIN_MODEL,
            cluster_model=CLUSTER_MODEL,
            fallback_model=FALLBACK_MODEL_1,
        )

    @classmethod
    def from_cli(
        cls,
        repo_path: str,
        output_dir: str,
        llm_base_url: str,
        llm_api_key: str,
        main_model: str,
        cluster_model: str,
        fallback_model: str = FALLBACK_MODEL_1,
        provider: str = "openai-compatible",
        aws_region: str = "us-east-1",
        api_version: str = "2024-12-01-preview",
        azure_deployment: str = "",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_token_per_module: int = DEFAULT_MAX_TOKEN_PER_MODULE,
        max_token_per_leaf_module: int = DEFAULT_MAX_TOKEN_PER_LEAF_MODULE,
        max_depth: int = MAX_DEPTH,
        agent_instructions: Optional[Dict[str, Any]] = None,
    ) -> "Config":
        """
        Create configuration for CLI context.

        Args:
            repo_path: Repository path
            output_dir: Output directory for generated docs
            llm_base_url: LLM API base URL
            llm_api_key: LLM API key
            main_model: Primary model
            cluster_model: Clustering model
            fallback_model: Fallback model
            provider: LLM provider type (openai-compatible, anthropic, bedrock, azure-openai)
            aws_region: AWS region for Bedrock provider
            api_version: Azure OpenAI API version
            azure_deployment: Azure OpenAI deployment name
            max_tokens: Maximum tokens for LLM response
            max_token_per_module: Maximum tokens per module for clustering
            max_token_per_leaf_module: Maximum tokens per leaf module
            max_depth: Maximum depth for hierarchical decomposition
            agent_instructions: Custom agent instructions dict

        Returns:
            Config instance
        """
        os.path.basename(os.path.normpath(repo_path))
        base_output_dir = os.path.join(output_dir, "temp")

        return cls(
            repo_path=repo_path,
            output_dir=base_output_dir,
            dependency_graph_dir=os.path.join(base_output_dir, DEPENDENCY_GRAPHS_DIR),
            docs_dir=output_dir,
            max_depth=max_depth,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            main_model=main_model,
            cluster_model=cluster_model,
            fallback_model=fallback_model,
            provider=provider,
            aws_region=aws_region,
            api_version=api_version,
            azure_deployment=azure_deployment,
            max_tokens=max_tokens,
            max_token_per_module=max_token_per_module,
            max_token_per_leaf_module=max_token_per_leaf_module,
            agent_instructions=agent_instructions,
        )
