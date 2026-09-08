"""Two-locale message catalog for text returned to agents.

Why this exists
---------------
Prompt titles/descriptions, the session instructions block, resource
metadata/bodies, tool-facing hints and on-disk artifacts were hard-coded in
Chinese.  MCP has no per-request language negotiation, so the language is
resolved **once per server process** (each IDE session spawns its own stdio
process, which is fine in practice).

Design decisions (product-maintenance, 2026-09):
- YAML resource files under ``locales/``: ``zh.yaml`` is the source of truth,
  ``en.yaml`` must fully cover it.
- **No runtime fallback for missing keys.** A missing key surfaces as an
  ``[missing-i18n-key ...]`` sentinel plus a warning; a pre-release key-set
  test (``tests/test_i18n.py``) guarantees the catalogs stay in sync, so a
  missing key at runtime is a bug that ships only if the test was skipped.
- Language resolution order:
  ``~/.codewiki/config.json`` ``lang`` field > ``$CODEWIKI_LANG`` env >
  OS locale (``zh*`` -> zh, anything else -> en) > ``zh``.
  An explicit-but-invalid value logs a warning and falls back to ``zh``.
  (This is not the same as the "no fallback for missing translation keys"
  rule above: it only governs how an unset/invalid language preference is
  defaulted.)

Usage
-----
    from codewiki.mcp import i18n
    i18n.init_lang()                 # once, at process start (idempotent)
    i18n.t("prompts.init_wiki.title")
    i18n.t("server.instructions")
    i18n.t("prompts.init_wiki.step", repo_path=repo)

Text blocks that contain no placeholders can be fetched with ``t(key)``.
Blocks with placeholders must be fetched with ``t(key, **vars)``: the
template syntax is ``str.format``, so literal ``{``/``}`` inside a template
are written ``{{``/``}}`` (JSON examples, PowerShell snippets etc.).
"""

from __future__ import annotations

import json
import locale as _locale_mod
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_LANG = "zh"
SUPPORTED = ("zh", "en")
MISSING_PREFIX = "[missing-i18n-key]"

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_DEFAULT_CONFIG_PATH = Path.home() / ".codewiki" / "config.json"

_lock = threading.RLock()
_catalogs: dict[str, dict[str, Any]] = {}
_lang: str = DEFAULT_LANG


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------


def _catalog_path(lang: str) -> Path:
    return _LOCALES_DIR / f"{lang}.yaml"


def _load_catalog(lang: str) -> dict[str, Any]:
    """Load one catalog file; never raises (missing/broken file -> empty)."""
    path = _catalog_path(lang)
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict):
            return data
        logger.error("i18n catalog %s is not a mapping; treating as empty", path)
        return {}
    except FileNotFoundError:
        logger.error("i18n catalog not found: %s", path)
        return {}
    except Exception as exc:  # noqa: BLE001 - catalog must never crash the server
        logger.error("failed to load i18n catalog %s: %s", path, exc)
        return {}


def _ensure_loaded() -> None:
    """Load zh + en catalogs once (lazy, thread-safe)."""
    if not _catalogs:
        with _lock:
            if not _catalogs:
                for lang in SUPPORTED:
                    _catalogs[lang] = _load_catalog(lang)


def _lookup(key: str, lang: Optional[str] = None) -> Optional[str]:
    """Resolve a dotted key against a catalog; None when absent."""
    _ensure_loaded()
    lang = lang or _lang
    node: Any = _catalogs.get(lang, {})
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


# ---------------------------------------------------------------------------
# Language resolution
# ---------------------------------------------------------------------------


def _read_config_lang(config_path: Path) -> str:
    """Read the ``lang`` field from a CodeWiki config.json ('' when absent)."""
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = json.load(fh)
        value = data.get("lang")
        if isinstance(value, str):
            return value.strip().lower()
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001 - bad config must not crash startup
        logger.warning("could not read language from %s: %s", config_path, exc)
    return ""


def _system_locale_code() -> str:
    """Return the current locale language code ('' when undetectable)."""
    try:
        code, _ = _locale_mod.getlocale()
        if code:
            return code
    except Exception:  # noqa: BLE001
        pass
    # Some minimal environments return (None, None) from getlocale().
    lang = os.environ.get("LANG") or os.environ.get("LC_ALL") or ""
    return lang.split(".")[0].replace("_", "-")


def resolve_lang(
    config_path: Optional[Path] = None,
    env_value: Optional[str] = None,
    locale_code: Optional[str] = None,
) -> str:
    """Resolve the process language.

    Resolution order (see module docstring): config file ``lang`` field >
    ``$CODEWIKI_LANG`` env > OS locale > ``zh``.

    Arguments are injectable for tests; ``None`` means "read from the real
    environment".
    """
    # 1) explicit config file value
    cfg_lang = _read_config_lang(config_path if config_path is not None else _DEFAULT_CONFIG_PATH)
    if cfg_lang:
        return cfg_lang if cfg_lang in SUPPORTED else _invalid("config", cfg_lang)

    # 2) explicit env value
    env_lang = (os.environ.get("CODEWIKI_LANG") if env_value is None else env_value) or ""
    env_lang = env_lang.strip().lower()
    if env_lang:
        return env_lang if env_lang in SUPPORTED else _invalid("env", env_lang)

    # 3) OS locale inference.
    # NOTE: Python reports Windows locales by language NAME, not by ISO code —
    # e.g. ('Chinese (Simplified)_China', '936') rather than ('zh_CN', ...).
    # Matching only on a "zh" prefix silently turned Chinese Windows into
    # English, so match both spellings.
    code = _system_locale_code() if locale_code is None else (locale_code or "")
    code = code.lower().replace("-", "_")
    if code.startswith("zh") or "chinese" in code:
        return "zh"
    if code:
        return "en"

    # 4) default
    return DEFAULT_LANG


def _invalid(source: str, value: str) -> str:
    logger.warning(
        "unsupported language %r from %s (expected one of %s); falling back to %r",
        value,
        source,
        ", ".join(SUPPORTED),
        DEFAULT_LANG,
    )
    return DEFAULT_LANG


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_lang() -> str:
    """Resolve and set the process language once (idempotent)."""
    global _lang
    with _lock:
        resolved = resolve_lang()
        if resolved != _lang:
            _lang = resolved
            _catalogs.clear()
            logger.info("i18n language set to %r", _lang)
        return _lang


def set_lang(lang: str) -> str:
    """Force a language (tests / explicit override)."""
    global _lang
    if lang not in SUPPORTED:
        raise ValueError(f"unsupported language: {lang!r} (expected one of {SUPPORTED})")
    with _lock:
        _lang = lang
        _catalogs.clear()
    return lang


def lang() -> str:
    return _lang


def t(key: str, **fmt: Any) -> str:
    """Fetch a localized string by dotted key, formatting placeholders.

    ``t(key)`` returns the raw template; use ``t(key, **vars)`` when the
    template contains ``{name}`` placeholders.  Missing keys never silently
    fall back — they return a ``[missing-i18n-key ...]`` sentinel (and log a
    warning) so the gap is visible; ``tests/test_i18n.py`` keeps zh/en in sync
    so this should not happen in a released build.
    """
    text = _lookup(key)
    if text is None:
        logger.warning("missing i18n key %r (lang=%s)", key, _lang)
        return f"{MISSING_PREFIX} {key}"
    if not fmt:
        return text
    try:
        return text.format(**fmt)
    except Exception as exc:  # noqa: BLE001 - surface as sentinel, never raise
        logger.warning("i18n format error for key %r: %s", key, exc)
        return f"{MISSING_PREFIX} {key} (format error: {exc})"


def all_keys(lang: str) -> list[str]:
    """Return every leaf key of a catalog as dotted paths (for tests)."""
    _ensure_loaded()
    data = _catalogs.get(lang, {})
    result: list[str] = []

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            for part, value in node.items():
                walk(value, f"{prefix}.{part}" if prefix else part)
        else:
            result.append(prefix)

    walk(data, "")
    return result
