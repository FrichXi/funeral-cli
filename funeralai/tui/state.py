"""Reactive application state for the TUI.

Maps to OpenCode's context/sync.tsx + context/local.tsx.
Centralized state that widgets observe via Textual's reactive system.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from funeralai.config import (
    get_api_key,
    get_default_provider,
    load_config,
    save_api_key,
    save_config,
)
from funeralai.analyzer import PROVIDERS


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_IDLE = "idle"
STATUS_INSPECTING = "inspecting"
STATUS_EXTRACTING = "extracting"
STATUS_ASKING = "asking"
STATUS_JUDGING = "judging"
STATUS_CHATTING = "chatting"
STATUS_DONE = "done"
STATUS_ERROR = "error"


# ---------------------------------------------------------------------------
# AppState
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    """Centralized TUI state. Used by the App and passed to screens/widgets."""

    # Provider / auth
    provider: str = ""
    api_key: str = ""
    model: str | None = None

    # Analysis status
    status: str = STATUS_IDLE
    status_detail: str = ""  # e.g. "检查 GitHub 仓库..."

    # Last input tracking (for retry, vote)
    last_input: str | None = None
    last_input_type: str | None = None  # "file" / "github" / "web" / "text"
    last_text: str | None = None
    last_inspection: dict | None = None
    last_red_flags: list[str] | None = None
    last_prompt_version: int | None = None

    # Results
    analyses: list[dict] = field(default_factory=list)
    current_result: dict | list[dict] | None = None

    # Whether user has explicitly configured a provider (via config.json)
    _configured_from_config: bool = False

    def init_from_config(self) -> None:
        """Load provider/key from config on startup."""
        result = get_default_provider()
        if result:
            self.provider, self.api_key = result
            self._configured_from_config = True
        else:
            # Try scan env vars — but don't mark as configured
            from funeralai.config import scan_env_keys
            found = scan_env_keys()
            if found:
                self.provider, self.api_key = found
                self._configured_from_config = False

    @property
    def has_provider(self) -> bool:
        return bool(self.provider and self.api_key)

    @property
    def needs_setup(self) -> bool:
        """True if user hasn't explicitly configured via setup (first run)."""
        return not self._configured_from_config

    @property
    def default_model(self) -> str:
        """Get the default model for current provider."""
        if self.model:
            return self.model
        info = PROVIDERS.get(self.provider, {})
        return info.get("default_model", "unknown")

    @property
    def provider_display(self) -> str:
        """e.g. 'deepseek (deepseek-chat)'"""
        return f"{self.provider} ({self.default_model})"

    def switch_provider(self, provider: str, api_key: str | None = None) -> bool:
        """Switch to a different provider. Returns True on success."""
        if provider not in PROVIDERS:
            return False
        key = api_key or get_api_key(provider)
        if not key:
            return False
        self.provider = provider
        self.api_key = key
        self.model = None  # reset to default
        return True

    def configure_provider(
        self,
        provider: str,
        api_key: str,
        *,
        configured: bool = True,
    ) -> None:
        """Apply a provider/key pair to the current session."""
        self.provider = provider
        self.api_key = api_key
        self.model = None
        self._configured_from_config = configured

    def switch_model(self, model: str) -> None:
        """Override model for current provider."""
        self.model = model

    def record_analysis(self, result: dict | list[dict]) -> None:
        """Record a completed analysis result."""
        self.analyses.append(result)
        self.current_result = result
        self.status = STATUS_DONE

    def can_retry(self) -> bool:
        """Can we re-run the last analysis?"""
        return self.last_text is not None

    def can_vote(self) -> bool:
        """Can we run multi-model vote on last input?"""
        return self.last_text is not None

    def configured_providers(self) -> list[str]:
        """Return list of providers that have API keys configured."""
        result = []
        for name in PROVIDERS:
            if get_api_key(name):
                result.append(name)
        return result

    def reset_analysis(self) -> None:
        """Reset analysis state for a new run."""
        self.status = STATUS_IDLE
        self.status_detail = ""
        self.current_result = None
