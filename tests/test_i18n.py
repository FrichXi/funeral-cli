"""Tests for funeralai.i18n — language detection, string registry, t() function."""

import os

import pytest

from funeralai import i18n
from funeralai.i18n import (
    PLACEHOLDER_KEYS,
    TIP_KEYS,
    _STRINGS,
    detect_ui_lang,
    get_lang,
    init_lang,
    set_lang,
    t,
)


# ── Helpers ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_lang():
    """Reset language to 'en' before each test."""
    set_lang("en")
    yield
    set_lang("en")


# ── 1. set_lang / get_lang ─────────────────────────────────────────────────

def test_set_lang_zh():
    set_lang("zh")
    assert get_lang() == "zh"


def test_set_lang_en():
    set_lang("zh")
    set_lang("en")
    assert get_lang() == "en"


def test_set_lang_invalid_ignored():
    set_lang("zh")
    set_lang("fr")  # unsupported, should be ignored
    assert get_lang() == "zh"


# ── 2. t() — known keys ───────────────────────────────────────────────────

def test_t_english():
    set_lang("en")
    assert t("slogan") == "be real"


def test_t_chinese():
    set_lang("zh")
    assert t("slogan") == "整点真实"


def test_t_switches_with_lang():
    set_lang("en")
    en = t("goodbye")
    set_lang("zh")
    zh = t("goodbye")
    assert en == "Goodbye"
    assert zh == "再见"


# ── 3. t() — unknown key returns key ──────────────────────────────────────

def test_t_unknown_key():
    assert t("nonexistent_key_xyz") == "nonexistent_key_xyz"


def test_t_empty_key():
    assert t("") == ""


# ── 4. t() — with kwargs ──────────────────────────────────────────────────

def test_t_with_kwargs_en():
    set_lang("en")
    result = t("switched", provider="deepseek", model="deepseek-chat")
    assert "deepseek" in result
    assert "deepseek-chat" in result


def test_t_with_kwargs_zh():
    set_lang("zh")
    result = t("switched", provider="openai", model="gpt-4o")
    assert "openai" in result
    assert "gpt-4o" in result


def test_t_with_partial_kwargs():
    """Missing kwargs should not crash — returns unformatted text."""
    set_lang("en")
    result = t("switched", provider="x")
    # Should return something (either formatted or original template)
    assert isinstance(result, str)
    assert len(result) > 0


# ── 5. init_lang() — default detection ────────────────────────────────────

def test_init_lang_defaults_to_en(monkeypatch):
    """Without config or locale hints, init_lang defaults to en."""
    # Remove locale env vars
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    # Patch _lang_from_config to return None (no config file)
    monkeypatch.setattr(i18n, "_lang_from_config", lambda: None)
    init_lang()
    assert get_lang() == "en"


def test_init_lang_respects_zh_locale(monkeypatch):
    """LANG=zh_CN.UTF-8 → zh."""
    monkeypatch.setattr(i18n, "_lang_from_config", lambda: None)
    monkeypatch.setenv("LC_ALL", "")
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    init_lang()
    assert get_lang() == "zh"


def test_init_lang_config_overrides_env(monkeypatch):
    """config.json lang=zh takes priority over LANG=en_US."""
    monkeypatch.setattr(i18n, "_lang_from_config", lambda: "zh")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    init_lang()
    assert get_lang() == "zh"


# ── 6. PLACEHOLDER_KEYS non-empty ─────────────────────────────────────────

def test_placeholder_keys_nonempty():
    assert len(PLACEHOLDER_KEYS) > 0


def test_placeholder_keys_all_registered():
    """All placeholder keys exist in _STRINGS."""
    for key in PLACEHOLDER_KEYS:
        assert key in _STRINGS, f"Placeholder key '{key}' not in _STRINGS"


def test_tip_keys_nonempty():
    assert len(TIP_KEYS) > 0


def test_tip_keys_all_registered():
    """All tip keys exist in _STRINGS."""
    for key in TIP_KEYS:
        assert key in _STRINGS, f"Tip key '{key}' not in _STRINGS"


# ── 7. status_chatting and other new strings exist ─────────────────────────

NEW_STATUS_KEYS = [
    "status_chatting",
    "status_extracting",
    "status_judging",
    "status_inspecting_github",
    "status_inspecting_web",
    "status_done",
    "status_asking",
]


@pytest.mark.parametrize("key", NEW_STATUS_KEYS)
def test_status_key_exists(key):
    """Status key is registered and has both zh and en."""
    assert key in _STRINGS
    entry = _STRINGS[key]
    assert "zh" in entry and entry["zh"]
    assert "en" in entry and entry["en"]


def test_status_chatting_values():
    set_lang("zh")
    assert "思考" in t("status_chatting")
    set_lang("en")
    assert "Think" in t("status_chatting") or "think" in t("status_chatting").lower()


# ── All string entries have both zh and en ─────────────────────────────────

@pytest.mark.parametrize("key", list(_STRINGS.keys()))
def test_every_string_has_both_languages(key):
    """Every registered string must provide both zh and en translations."""
    entry = _STRINGS[key]
    assert "zh" in entry, f"Key '{key}' missing 'zh'"
    assert "en" in entry, f"Key '{key}' missing 'en'"
    assert entry["zh"], f"Key '{key}' has empty 'zh'"
    assert entry["en"], f"Key '{key}' has empty 'en'"
