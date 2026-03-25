"""Tests for funeralai.tui.state — AppState and status constants."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from funeralai.analyzer import PROVIDERS
from funeralai.tui.state import (
    STATUS_ASKING,
    STATUS_CHATTING,
    STATUS_DONE,
    STATUS_ERROR,
    STATUS_EXTRACTING,
    STATUS_IDLE,
    STATUS_INSPECTING,
    STATUS_JUDGING,
    AppState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state() -> AppState:
    """Fresh AppState with no config side-effects."""
    return AppState()


@pytest.fixture()
def configured_state() -> AppState:
    """AppState pre-configured with a provider."""
    s = AppState()
    s.provider = "deepseek"
    s.api_key = "sk-test-key-123"
    s._configured_from_config = True
    return s


@pytest.fixture()
def fake_config_dir(tmp_path: Path):
    """Patch CONFIG_PATH to a temp directory so tests never touch real config."""
    fake_path = tmp_path / "config.json"
    with patch("funeralai.config.CONFIG_PATH", fake_path):
        yield fake_path


# ---------------------------------------------------------------------------
# 1. Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_provider_empty(self, state: AppState):
        assert state.provider == ""

    def test_api_key_empty(self, state: AppState):
        assert state.api_key == ""

    def test_model_none(self, state: AppState):
        assert state.model is None

    def test_status_idle(self, state: AppState):
        assert state.status == STATUS_IDLE

    def test_status_detail_empty(self, state: AppState):
        assert state.status_detail == ""

    def test_last_input_none(self, state: AppState):
        assert state.last_input is None
        assert state.last_input_type is None
        assert state.last_text is None
        assert state.last_inspection is None
        assert state.last_red_flags is None
        assert state.last_prompt_version is None

    def test_analyses_empty_list(self, state: AppState):
        assert state.analyses == []

    def test_current_result_none(self, state: AppState):
        assert state.current_result is None

    def test_configured_from_config_false(self, state: AppState):
        assert state._configured_from_config is False

    def test_analyses_not_shared_across_instances(self):
        """Each AppState instance gets its own analyses list (field default_factory)."""
        a = AppState()
        b = AppState()
        a.analyses.append({"x": 1})
        assert b.analyses == []


# ---------------------------------------------------------------------------
# 2. has_provider
# ---------------------------------------------------------------------------


class TestHasProvider:
    def test_false_when_both_empty(self, state: AppState):
        assert state.has_provider is False

    def test_false_when_only_provider(self, state: AppState):
        state.provider = "anthropic"
        assert state.has_provider is False

    def test_false_when_only_api_key(self, state: AppState):
        state.api_key = "sk-abc"
        assert state.has_provider is False

    def test_true_when_both_set(self, state: AppState):
        state.provider = "anthropic"
        state.api_key = "sk-ant-xxx"
        assert state.has_provider is True


# ---------------------------------------------------------------------------
# 3. needs_setup
# ---------------------------------------------------------------------------


class TestNeedsSetup:
    def test_true_by_default(self, state: AppState):
        assert state.needs_setup is True

    def test_false_when_configured(self, configured_state: AppState):
        assert configured_state.needs_setup is False

    def test_true_after_env_scan(self, state: AppState):
        """Provider found via env scan still needs explicit setup."""
        state.provider = "openai"
        state.api_key = "sk-env"
        state._configured_from_config = False
        assert state.needs_setup is True

    def test_false_after_configure_provider(self, state: AppState):
        state.configure_provider("anthropic", "sk-ant-test", configured=True)
        assert state.needs_setup is False


# ---------------------------------------------------------------------------
# 4. default_model
# ---------------------------------------------------------------------------


class TestDefaultModel:
    def test_returns_custom_model_when_set(self, configured_state: AppState):
        configured_state.model = "deepseek-reasoner"
        assert configured_state.default_model == "deepseek-reasoner"

    def test_returns_provider_default_when_no_custom(self, configured_state: AppState):
        assert configured_state.model is None
        assert configured_state.default_model == PROVIDERS["deepseek"]["default_model"]

    def test_returns_unknown_for_empty_provider(self, state: AppState):
        assert state.default_model == "unknown"

    @pytest.mark.parametrize("provider_name", list(PROVIDERS.keys()))
    def test_all_providers_have_known_default(self, provider_name: str):
        s = AppState()
        s.provider = provider_name
        assert s.default_model != "unknown"
        assert s.default_model == PROVIDERS[provider_name]["default_model"]


# ---------------------------------------------------------------------------
# 5. provider_display
# ---------------------------------------------------------------------------


class TestProviderDisplay:
    def test_format(self, configured_state: AppState):
        expected_model = PROVIDERS["deepseek"]["default_model"]
        assert configured_state.provider_display == f"deepseek ({expected_model})"

    def test_with_custom_model(self, configured_state: AppState):
        configured_state.model = "deepseek-reasoner"
        assert configured_state.provider_display == "deepseek (deepseek-reasoner)"

    def test_empty_provider(self, state: AppState):
        assert state.provider_display == " (unknown)"


# ---------------------------------------------------------------------------
# 6. switch_provider
# ---------------------------------------------------------------------------


class TestSwitchProvider:
    def test_success_with_explicit_key(self, state: AppState):
        result = state.switch_provider("anthropic", api_key="sk-ant-test")
        assert result is True
        assert state.provider == "anthropic"
        assert state.api_key == "sk-ant-test"
        assert state.model is None

    def test_resets_model_on_switch(self, configured_state: AppState):
        configured_state.model = "custom-model"
        configured_state.switch_provider("openai", api_key="sk-test")
        assert configured_state.model is None

    def test_fails_for_unknown_provider(self, state: AppState):
        result = state.switch_provider("nonexistent", api_key="key")
        assert result is False
        assert state.provider == ""  # unchanged

    def test_fails_when_no_key_available(self, fake_config_dir):
        """Fail when provider exists but no API key (env or config)."""
        s = AppState()
        # Ensure no env var is set for anthropic
        with patch.dict("os.environ", {}, clear=False):
            env_var = "ANTHROPIC_API_KEY"
            environ_copy = dict(__import__("os").environ)
            environ_copy.pop(env_var, None)
            with patch.dict("os.environ", environ_copy, clear=True):
                result = s.switch_provider("anthropic")
                assert result is False

    def test_success_with_config_key(self, fake_config_dir):
        """Provider key found in config.json."""
        config = {"keys": {"anthropic": "sk-ant-from-config"}}
        fake_config_dir.write_text(json.dumps(config), encoding="utf-8")
        s = AppState()
        # Clear env var so config is used
        with patch.dict("os.environ", {}, clear=True):
            result = s.switch_provider("anthropic")
            assert result is True
            assert s.api_key == "sk-ant-from-config"

    def test_success_with_env_key(self, fake_config_dir):
        """Provider key found in environment variable."""
        s = AppState()
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-env-deep"}, clear=True):
            result = s.switch_provider("deepseek")
            assert result is True
            assert s.api_key == "sk-env-deep"


# ---------------------------------------------------------------------------
# 7. switch_model
# ---------------------------------------------------------------------------


class TestSwitchModel:
    def test_sets_model(self, configured_state: AppState):
        configured_state.switch_model("deepseek-reasoner")
        assert configured_state.model == "deepseek-reasoner"

    def test_overrides_default(self, configured_state: AppState):
        configured_state.switch_model("custom-v2")
        assert configured_state.default_model == "custom-v2"


# ---------------------------------------------------------------------------
# 8. record_analysis
# ---------------------------------------------------------------------------


class TestRecordAnalysis:
    def test_appends_to_analyses(self, state: AppState):
        r1 = {"verdict": "ok"}
        r2 = {"verdict": "nope"}
        state.record_analysis(r1)
        state.record_analysis(r2)
        assert state.analyses == [r1, r2]

    def test_updates_current_result(self, state: AppState):
        r = {"verdict": "interesting"}
        state.record_analysis(r)
        assert state.current_result is r

    def test_current_result_is_latest(self, state: AppState):
        r1 = {"verdict": "first"}
        r2 = {"verdict": "second"}
        state.record_analysis(r1)
        state.record_analysis(r2)
        assert state.current_result is r2

    def test_sets_status_done(self, state: AppState):
        state.status = STATUS_EXTRACTING
        state.record_analysis({"verdict": "done"})
        assert state.status == STATUS_DONE


# ---------------------------------------------------------------------------
# 9. can_retry / can_vote
# ---------------------------------------------------------------------------


class TestCanRetryAndVote:
    def test_cannot_retry_initially(self, state: AppState):
        assert state.can_retry() is False

    def test_cannot_vote_initially(self, state: AppState):
        assert state.can_vote() is False

    def test_can_retry_after_last_text_set(self, state: AppState):
        state.last_text = "some analysis text"
        assert state.can_retry() is True

    def test_can_vote_after_last_text_set(self, state: AppState):
        state.last_text = "some analysis text"
        assert state.can_vote() is True

    def test_cannot_retry_when_last_text_none(self, state: AppState):
        state.last_input = "https://example.com"
        state.last_input_type = "web"
        assert state.can_retry() is False

    def test_cannot_vote_when_last_text_none(self, state: AppState):
        state.last_input = "/path/to/file"
        state.last_input_type = "file"
        assert state.can_vote() is False


# ---------------------------------------------------------------------------
# 10. reset_analysis
# ---------------------------------------------------------------------------


class TestResetAnalysis:
    def test_resets_status_to_idle(self, state: AppState):
        state.status = STATUS_JUDGING
        state.reset_analysis()
        assert state.status == STATUS_IDLE

    def test_clears_status_detail(self, state: AppState):
        state.status_detail = "processing..."
        state.reset_analysis()
        assert state.status_detail == ""

    def test_clears_current_result(self, state: AppState):
        state.current_result = {"verdict": "old"}
        state.reset_analysis()
        assert state.current_result is None

    def test_preserves_analyses_history(self, state: AppState):
        r = {"verdict": "keep me"}
        state.analyses.append(r)
        state.current_result = r
        state.reset_analysis()
        assert state.analyses == [r]

    def test_preserves_provider(self, configured_state: AppState):
        configured_state.status = STATUS_ERROR
        configured_state.reset_analysis()
        assert configured_state.provider == "deepseek"
        assert configured_state.api_key == "sk-test-key-123"

    def test_preserves_last_input(self, state: AppState):
        state.last_text = "some text"
        state.last_input = "file.md"
        state.reset_analysis()
        assert state.last_text == "some text"
        assert state.last_input == "file.md"


# ---------------------------------------------------------------------------
# 11. configured_providers
# ---------------------------------------------------------------------------


class TestConfiguredProviders:
    def test_empty_when_no_keys(self, fake_config_dir):
        s = AppState()
        with patch.dict("os.environ", {}, clear=True):
            result = s.configured_providers()
            assert result == []

    def test_returns_providers_with_env_keys(self, fake_config_dir):
        s = AppState()
        with patch.dict(
            "os.environ",
            {"ANTHROPIC_API_KEY": "sk-ant-x", "DEEPSEEK_API_KEY": "sk-ds-x"},
            clear=True,
        ):
            result = s.configured_providers()
            assert "anthropic" in result
            assert "deepseek" in result

    def test_returns_providers_with_config_keys(self, fake_config_dir):
        config = {"keys": {"openai": "sk-cfg-openai", "gemini": "AIzaSy-cfg"}}
        fake_config_dir.write_text(json.dumps(config), encoding="utf-8")
        s = AppState()
        with patch.dict("os.environ", {}, clear=True):
            result = s.configured_providers()
            assert "openai" in result
            assert "gemini" in result
            assert "anthropic" not in result


# ---------------------------------------------------------------------------
# 12. Status constants completeness
# ---------------------------------------------------------------------------


class TestStatusConstants:
    EXPECTED_STATUSES = {
        "STATUS_IDLE": "idle",
        "STATUS_INSPECTING": "inspecting",
        "STATUS_EXTRACTING": "extracting",
        "STATUS_ASKING": "asking",
        "STATUS_JUDGING": "judging",
        "STATUS_CHATTING": "chatting",
        "STATUS_DONE": "done",
        "STATUS_ERROR": "error",
    }

    def test_all_status_constants_defined(self):
        import funeralai.tui.state as state_mod

        for name, value in self.EXPECTED_STATUSES.items():
            assert hasattr(state_mod, name), f"Missing constant: {name}"
            assert getattr(state_mod, name) == value

    def test_status_values_are_unique(self):
        import funeralai.tui.state as state_mod

        values = [
            getattr(state_mod, name) for name in self.EXPECTED_STATUSES
        ]
        assert len(values) == len(set(values)), "Duplicate status values found"

    def test_all_status_values_are_strings(self):
        import funeralai.tui.state as state_mod

        for name in self.EXPECTED_STATUSES:
            val = getattr(state_mod, name)
            assert isinstance(val, str), f"{name} should be str, got {type(val)}"


# ---------------------------------------------------------------------------
# configure_provider (used by setup flow)
# ---------------------------------------------------------------------------


class TestConfigureProvider:
    def test_sets_all_fields(self, state: AppState):
        state.configure_provider("anthropic", "sk-ant-new")
        assert state.provider == "anthropic"
        assert state.api_key == "sk-ant-new"
        assert state.model is None
        assert state._configured_from_config is True

    def test_resets_model(self, state: AppState):
        state.model = "old-model"
        state.configure_provider("openai", "sk-new")
        assert state.model is None

    def test_configured_false(self, state: AppState):
        state.configure_provider("openai", "sk-env", configured=False)
        assert state._configured_from_config is False
        assert state.needs_setup is True
