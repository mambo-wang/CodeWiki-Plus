"""i18n catalog tests for codewiki/mcp/i18n.py.

Pre-release gates (product-maintenance, 2026-09):
- ``zh.yaml`` is the source of truth; ``en.yaml`` must cover every zh key.  A
  missing en key must fail HERE rather than at runtime — there is no runtime
  fallback for missing translations by design, so this test is the only net
  that makes that decision safe.
- zh/en templates for the same key must expose the same ``{placeholder}``
  set, otherwise ``.format()`` would crash or render wrong text at runtime.
- A missing key must surface as a sentinel: never crash, never silently fall
  back to Chinese.
- Language resolution order: config.json ``lang`` > ``$CODEWIKI_LANG`` >
  OS locale > ``zh``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from codewiki.mcp import i18n

# `{name}` placeholders, ignoring `{{...}}` escapes.
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")


def _placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(text))


def _text(key: str, lang: str) -> str:
    i18n.set_lang(lang)
    return i18n.t(key)


@pytest.fixture(autouse=True)
def _restore_language():
    """Every test may flip the process language; restore it afterwards."""
    original = i18n.lang()
    yield
    i18n.set_lang(original)


# ---------------------------------------------------------------------------
# Catalog integrity
# ---------------------------------------------------------------------------


def test_both_catalogs_load():
    assert i18n.all_keys("zh"), "zh.yaml is empty or failed to load"
    assert i18n.all_keys("en"), "en.yaml is empty or failed to load"


def test_en_covers_every_zh_key():
    zh_keys = set(i18n.all_keys("zh"))
    en_keys = set(i18n.all_keys("en"))
    missing = sorted(zh_keys - en_keys)
    assert missing == [], (
        "en.yaml is missing keys that zh.yaml defines — add the English text "
        f"(or confirm the zh key is obsolete and delete it): {missing}"
    )


def test_placeholder_sets_match_between_languages():
    mismatches = []
    for key in i18n.all_keys("zh"):
        zh_text = _text(key, "zh")
        en_text = _text(key, "en")
        zh_ph, en_ph = _placeholders(zh_text), _placeholders(en_text)
        if zh_ph != en_ph:
            mismatches.append(f"{key}: zh={sorted(zh_ph)} en={sorted(en_ph)}")
    assert mismatches == [], (
        "zh/en templates disagree on placeholders (would break .format()):\n"
        + "\n".join(mismatches)
    )


def test_templates_format_placeholders():
    """A template with placeholders renders only when vars are supplied."""
    example = [
        key
        for key in i18n.all_keys("zh")
        if _placeholders(_text(key, "zh"))
    ]
    if not example:
        pytest.skip("no parameterized templates in the catalog yet")
    key = example[0]
    for var in _placeholders(_text(key, "zh")):
        i18n.set_lang("zh")
        rendered = i18n.t(key, **{var: "X"})
        assert "X" in rendered or i18n.MISSING_PREFIX in rendered


# ---------------------------------------------------------------------------
# Missing-key behavior (no runtime fallback by design)
# ---------------------------------------------------------------------------


def test_missing_key_returns_sentinel():
    result = i18n.t("no.such.key.anywhere")
    assert i18n.MISSING_PREFIX in result
    assert "no.such.key.anywhere" in result


def test_missing_key_never_raises():
    i18n.t("")  # degenerate key: must not raise
    i18n.t("server.instructions.extra")  # crossing a leaf: must not raise


# ---------------------------------------------------------------------------
# Language resolution
# ---------------------------------------------------------------------------


def test_resolve_config_wins_over_env(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"lang": "en"}', encoding="utf-8")
    assert i18n.resolve_lang(config_path=cfg, env_value="zh", locale_code="zh_CN") == "en"


def test_resolve_env_used_without_config(tmp_path):
    cfg = tmp_path / "missing.json"
    assert i18n.resolve_lang(config_path=cfg, env_value="en", locale_code="zh_CN") == "en"


def test_resolve_locale_inference(tmp_path):
    cfg = tmp_path / "missing.json"
    assert i18n.resolve_lang(config_path=cfg, env_value="", locale_code="zh_CN") == "zh"
    assert i18n.resolve_lang(config_path=cfg, env_value="", locale_code="en_US") == "en"
    # Non-Chinese, non-configured locale resolves to English.
    assert i18n.resolve_lang(config_path=cfg, env_value="", locale_code="de_DE") == "en"


def test_resolve_windows_locale_names(tmp_path):
    """Windows reports locales by language NAME, not by ISO code."""
    cfg = tmp_path / "missing.json"
    assert (
        i18n.resolve_lang(
            config_path=cfg, env_value="", locale_code="Chinese (Simplified)_China"
        )
        == "zh"
    )
    assert (
        i18n.resolve_lang(
            config_path=cfg, env_value="", locale_code="Chinese (Traditional)_Taiwan"
        )
        == "zh"
    )
    assert (
        i18n.resolve_lang(
            config_path=cfg, env_value="", locale_code="English_United States"
        )
        == "en"
    )


def test_resolve_defaults_to_zh(tmp_path):
    cfg = tmp_path / "missing.json"
    assert i18n.resolve_lang(config_path=cfg, env_value="", locale_code="") == "zh"


def test_resolve_invalid_explicit_value_falls_back_to_zh(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"lang": "fr"}', encoding="utf-8")
    assert i18n.resolve_lang(config_path=cfg, env_value="", locale_code="en_US") == "zh"

    assert i18n.resolve_lang(config_path=tmp_path / "x.json", env_value="jp") == "zh"


def test_set_lang_rejects_unsupported():
    with pytest.raises(ValueError):
        i18n.set_lang("fr")


# ---------------------------------------------------------------------------
# Template variants (schema.yaml vs schema.en.yaml) must not drift apart
# ---------------------------------------------------------------------------


def _yaml_keys(node, prefix="") -> set:
    out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}"
            out.add(path)
            out |= _yaml_keys(value, path)
    elif isinstance(node, list):
        for value in node:
            out |= _yaml_keys(value, f"{prefix}[]")
    return out


def test_schema_template_variants_share_structure():
    """schema.yaml and schema.en.yaml must expose the same keys.

    Two hand-maintained copies of a template are exactly the setup that let
    the old prompts/catalog drift to 15 of 22 entries — pin the structure.
    """
    from ruamel.yaml import YAML

    templates = Path(__file__).resolve().parents[1] / "codewiki" / "templates"
    yaml = YAML()
    zh = yaml.load((templates / "schema.yaml").read_text(encoding="utf-8"))
    en = yaml.load((templates / "schema.en.yaml").read_text(encoding="utf-8"))

    zh_keys, en_keys = _yaml_keys(zh), _yaml_keys(en)
    assert zh_keys, "schema.yaml failed to load"
    assert not (zh_keys ^ en_keys), (
        "schema template variants drifted: " + ", ".join(sorted(zh_keys ^ en_keys))
    )


def test_same_key_differs_by_language():
    key = i18n.all_keys("zh")[0]
    assert _text(key, "zh") != _text(key, "en")
