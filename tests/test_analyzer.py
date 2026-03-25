"""Tests for funeralai.analyzer — structure, helpers, and constants.

No real LLM calls. Tests cover PROVIDERS dict, load_prompt(), parse_json(),
default_model values, and prompt_version mapping.
"""

import json
from pathlib import Path

import pytest

from funeralai.analyzer import (
    PROVIDERS,
    _EXTRACT_PATHS,
    _JUDGE_PROMPTS,
    _PIPELINE_NAMES,
    _assemble_result,
    _synthesize_votes,
    load_prompt,
    parse_json,
)
from funeralai.recommendations import DEFAULT_RECOMMENDATION


# ── Paths ──────────────────────────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "funeralai" / "prompts"


# ── 1. PROVIDERS dict completeness ─────────────────────────────────────────

EXPECTED_PROVIDERS = [
    "anthropic", "openai", "gemini", "kimi",
    "minimax", "deepseek", "zhipu", "qwen",
]


def test_providers_all_present():
    """All 8 providers are registered."""
    assert sorted(PROVIDERS.keys()) == sorted(EXPECTED_PROVIDERS)


@pytest.mark.parametrize("name", EXPECTED_PROVIDERS)
def test_provider_has_required_fields(name):
    """Each provider has default_model, env_key, and type."""
    cfg = PROVIDERS[name]
    assert "default_model" in cfg and cfg["default_model"]
    assert "env_key" in cfg and cfg["env_key"]
    assert "type" in cfg and cfg["type"] in ("openai", "anthropic")


@pytest.mark.parametrize("name", EXPECTED_PROVIDERS)
def test_provider_base_url_when_needed(name):
    """Non-first-party providers must have base_url; first-party may be None."""
    cfg = PROVIDERS[name]
    # First-party providers (openai, anthropic) can have base_url=None
    if name not in ("openai", "anthropic"):
        assert cfg.get("base_url"), f"{name} should have a base_url"


# ── 2. load_prompt() — all prompt files loadable ───────────────────────────

ALL_PROMPT_FILES = [
    "extract_local.md", "extract_github.md", "extract_web.md",
    "judge_ad_detect.md", "judge_summary.md", "judge_evidence.md", "judge_verdict.md",
    "ask.md", "chat.md",
    # Legacy single-judge prompts (kept for compat)
    "judge_local.md", "judge_github.md", "judge_web.md",
]


@pytest.mark.parametrize("filename", ALL_PROMPT_FILES)
def test_load_prompt_file_exists(filename):
    """Prompt file exists and load_prompt returns non-empty string."""
    path = PROMPTS_DIR / filename
    assert path.exists(), f"Missing prompt file: {path}"
    # Clear lru_cache to avoid cross-test pollution
    load_prompt.cache_clear()
    content = load_prompt(path)
    assert isinstance(content, str)
    assert len(content) > 10, f"Prompt file {filename} is suspiciously short"


def test_load_prompt_caches():
    """load_prompt uses lru_cache — second call returns same object."""
    load_prompt.cache_clear()
    path = PROMPTS_DIR / "ask.md"
    first = load_prompt(path)
    second = load_prompt(path)
    assert first is second


# ── 3. parse_json() ────────────────────────────────────────────────────────

def test_parse_json_plain_object():
    assert parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_plain_array():
    assert parse_json('[1, 2, 3]') == [1, 2, 3]


def test_parse_json_markdown_fence():
    text = '```json\n{"key": "value"}\n```'
    assert parse_json(text) == {"key": "value"}


def test_parse_json_fence_without_lang_tag():
    text = '```\n{"key": "value"}\n```'
    assert parse_json(text) == {"key": "value"}


def test_parse_json_embedded_in_text():
    text = 'Here is the result:\n{"verdict": "ok"}\nDone.'
    result = parse_json(text)
    assert result == {"verdict": "ok"}


def test_parse_json_embedded_array():
    text = 'Some text [1, 2, 3] more text'
    assert parse_json(text) == [1, 2, 3]


def test_parse_json_invalid_returns_none():
    assert parse_json("not json at all") is None


def test_parse_json_empty_string():
    assert parse_json("") is None


def test_parse_json_whitespace():
    result = parse_json('  \n  {"x": true}  \n  ')
    assert result == {"x": True}


def test_parse_json_nested_objects():
    obj = {"outer": {"inner": [1, 2]}, "flag": True}
    assert parse_json(json.dumps(obj)) == obj


# ── 4. Default model values ───────────────────────────────────────────────

EXPECTED_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-3.1-pro-preview",
    "kimi": "kimi-k2.5",
    "minimax": "MiniMax-M2.7",
    "deepseek": "deepseek-chat",
    "zhipu": "glm-4.7",
    "qwen": "qwen-plus",
}


@pytest.mark.parametrize("provider,expected_model", EXPECTED_MODELS.items())
def test_default_model_value(provider, expected_model):
    """Default model for each provider matches expected value."""
    assert PROVIDERS[provider]["default_model"] == expected_model


# ── 5. prompt_version mapping ──────────────────────────────────────────────

def test_prompt_version_mapping():
    """prompt_version 1=local, 2=github, 3=web."""
    assert _PIPELINE_NAMES == {1: "local", 2: "github", 3: "web"}


def test_extract_paths_mapping():
    """Extract prompt paths correspond to the three pipelines."""
    assert set(_EXTRACT_PATHS.keys()) == {1, 2, 3}
    assert _EXTRACT_PATHS[1].name == "extract_local.md"
    assert _EXTRACT_PATHS[2].name == "extract_github.md"
    assert _EXTRACT_PATHS[3].name == "extract_web.md"


def test_judge_prompts_keys():
    """Parallel judge has exactly 4 prompts."""
    assert set(_JUDGE_PROMPTS.keys()) == {"ad_detect", "summary", "evidence", "verdict"}


def test_assemble_result_uses_default_recommendation_when_verdict_missing_label():
    result = _assemble_result(
        {
            "ad_detect": {"article_type": "evaluable"},
            "summary": {"primary_product": "Tabbit", "product_reality": "一个浏览器"},
            "evidence": {"evidence": []},
            "verdict": {"verdict": "材料不足", "information_completeness": "low"},
        }
    )

    assert result["investment_recommendation"] == DEFAULT_RECOMMENDATION


def test_synthesize_votes_uses_default_recommendation_when_empty():
    result = _synthesize_votes([])

    assert result["recommendation"] == DEFAULT_RECOMMENDATION
