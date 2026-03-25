"""Tests for funeralai.config — persistence, key detection, env scanning.

Uses tmp_path to isolate all tests from the real ~/.config/funeralai/config.json.
"""

import json
import os

import pytest

from funeralai import config
from funeralai.config import (
    PROVIDERS_ENV,
    detect_provider_from_key,
    get_api_key,
    get_default_provider,
    load_config,
    save_api_key,
    save_config,
    scan_env_keys,
)


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect CONFIG_PATH to a temp directory for every test."""
    fake_config = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", fake_config)
    # Clear provider env vars to avoid leaking real keys into tests
    for env_var in PROVIDERS_ENV.values():
        monkeypatch.delenv(env_var, raising=False)
    yield fake_config


# ── 1. load_config — file not found → {} ──────────────────────────────────

def test_load_config_missing_file():
    """Non-existent config file returns empty dict."""
    assert load_config() == {}


def test_load_config_corrupted_file(isolate_config):
    """Corrupted JSON returns empty dict."""
    isolate_config.write_text("not json {{{", encoding="utf-8")
    assert load_config() == {}


# ── 2. save_config + load_config roundtrip ─────────────────────────────────

def test_save_and_load_roundtrip():
    data = {"default_provider": "anthropic", "keys": {"anthropic": "sk-ant-test"}, "lang": "zh"}
    save_config(data)
    loaded = load_config()
    assert loaded == data


def test_save_creates_parent_dirs(tmp_path, monkeypatch):
    nested = tmp_path / "deep" / "nested" / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", nested)
    save_config({"test": True})
    assert nested.exists()
    assert load_config() == {"test": True}


# ── 3. get_api_key — from env var ─────────────────────────────────────────

def test_get_api_key_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
    assert get_api_key("anthropic") == "sk-ant-env-key"


def test_get_api_key_env_takes_priority(monkeypatch):
    """Env var takes priority over config file."""
    save_config({"keys": {"anthropic": "sk-ant-config-key"}})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
    assert get_api_key("anthropic") == "sk-ant-env-key"


# ── 4. get_api_key — from config file ─────────────────────────────────────

def test_get_api_key_from_config():
    save_config({"keys": {"openai": "sk-config-key"}})
    assert get_api_key("openai") == "sk-config-key"


def test_get_api_key_missing_returns_none():
    assert get_api_key("deepseek") is None


def test_get_api_key_empty_string_returns_none():
    save_config({"keys": {"openai": "  "}})
    assert get_api_key("openai") is None


# ── 5. save_api_key — saves and sets default ──────────────────────────────

def test_save_api_key_sets_default():
    save_api_key("deepseek", "ds-test-key")
    loaded = load_config()
    assert loaded["keys"]["deepseek"] == "ds-test-key"
    assert loaded["default_provider"] == "deepseek"


def test_save_api_key_preserves_existing():
    save_config({"keys": {"anthropic": "sk-ant-old"}, "lang": "zh"})
    save_api_key("openai", "sk-new-key")
    loaded = load_config()
    # Old key preserved
    assert loaded["keys"]["anthropic"] == "sk-ant-old"
    # New key added
    assert loaded["keys"]["openai"] == "sk-new-key"
    # Default switched to new provider
    assert loaded["default_provider"] == "openai"
    # Extra fields preserved
    assert loaded["lang"] == "zh"


def test_save_api_key_sets_env_var(monkeypatch):
    """save_api_key also sets the env var for the current process."""
    save_api_key("anthropic", "sk-ant-process")
    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-process"


# ── 6. detect_provider_from_key ────────────────────────────────────────────

@pytest.mark.parametrize("key,expected", [
    ("sk-ant-abc123", "anthropic"),
    ("sk-abc123", "openai"),
    ("AIzaSyXXXXXX", "gemini"),
    ("some-random-token-no-prefix", None),
    ("", None),
])
def test_detect_provider_from_key(key, expected):
    assert detect_provider_from_key(key) == expected


def test_detect_provider_strips_whitespace():
    assert detect_provider_from_key("  sk-ant-test  ") == "anthropic"


# ── 7. scan_env_keys ──────────────────────────────────────────────────────

def test_scan_env_keys_none_set():
    """No env vars set → None."""
    assert scan_env_keys() is None


def test_scan_env_keys_finds_first(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    result = scan_env_keys()
    assert result is not None
    provider, key = result
    assert provider == "deepseek"
    assert key == "ds-key"


def test_scan_env_keys_priority_order(monkeypatch):
    """Anthropic comes before deepseek in PROVIDERS_ENV order."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-first")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-second")
    result = scan_env_keys()
    assert result is not None
    assert result[0] == "anthropic"


def test_scan_env_keys_skips_empty(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    result = scan_env_keys()
    assert result is not None
    assert result[0] == "openai"


# ── 8. get_default_provider ───────────────────────────────────────────────

def test_get_default_provider_no_config():
    assert get_default_provider() is None


def test_get_default_provider_no_key():
    save_config({"default_provider": "anthropic", "keys": {}})
    assert get_default_provider() is None


def test_get_default_provider_success():
    save_config({"default_provider": "anthropic", "keys": {"anthropic": "sk-ant-saved"}})
    result = get_default_provider()
    assert result == ("anthropic", "sk-ant-saved")


def test_get_default_provider_empty_provider_string():
    save_config({"default_provider": "", "keys": {"anthropic": "sk-ant-saved"}})
    assert get_default_provider() is None


# ── PROVIDERS_ENV completeness ─────────────────────────────────────────────

def test_providers_env_has_all_8():
    assert len(PROVIDERS_ENV) == 8
    expected = {"anthropic", "openai", "gemini", "kimi", "minimax", "deepseek", "zhipu", "qwen"}
    assert set(PROVIDERS_ENV.keys()) == expected
