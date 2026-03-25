"""Credential validation and interactive recovery helpers."""

from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass

from funeralai.analyzer import (
    PROVIDERS,
    _call_anthropic,
    _call_openai_compat,
)
from funeralai.config import get_api_key, save_api_key
from funeralai.i18n import init_lang, t

_PROVIDER_ORDER = [
    "anthropic",
    "openai",
    "deepseek",
    "gemini",
    "qwen",
    "kimi",
    "minimax",
    "zhipu",
]


@dataclass(frozen=True)
class ProviderIssue:
    """Normalized provider/auth issue used by CLI and TUI recovery flows."""

    category: str
    message: str


@dataclass(frozen=True)
class VoteProviderIssue:
    """A recoverable provider issue found inside a vote result."""

    provider: str
    model: str
    raw_error: str
    issue: ProviderIssue


def mask_key(key: str) -> str:
    """Mask a credential for status messages."""
    if len(key) <= 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


def classify_provider_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
) -> ProviderIssue:
    """Map SDK/library exceptions to a small set of user-facing categories."""
    msg = str(error).strip()
    low = msg.lower()
    provider_label = provider or "当前 provider"
    model_label = model or "当前模型"

    if any(
        kw in low
        for kw in (
            "需要设置环境变量",
            "api key required",
            "no api key",
            "missing api key",
        )
    ):
        return ProviderIssue(
            "missing_key",
            f"{provider_label} 还没有可用的 API key。请输入一个新的 key，或切换其他 Provider。",
        )

    if any(
        kw in low
        for kw in (
            "authentication_error",
            "invalid x-api-key",
            "invalid api key",
            "invalid_api_key",
            "incorrect api key",
            "unauthorized",
            "authentication failed",
            "401",
            "invalid key",
        )
    ):
        return ProviderIssue(
            "auth",
            f"{provider_label} 的 API key 无效或已过期。请重新输入，或切换其他 Provider。",
        )

    if any(
        kw in low
        for kw in (
            "rate_limit",
            "too many requests",
            "429",
        )
    ):
        return ProviderIssue(
            "rate_limit",
            f"{provider_label} 当前触发限流。你可以稍后重试，或先切换其他 Provider。",
        )

    if any(
        kw in low
        for kw in (
            "insufficient_quota",
            "billing",
            "exceeded your current quota",
            "credit balance is too low",
        )
    ):
        return ProviderIssue(
            "quota",
            f"{provider_label} 当前额度不足。请检查账户余额，或切换其他 Provider。",
        )

    if any(
        kw in low
        for kw in (
            "connection error",
            "connection",
            "timeout",
            "dns",
            "unreachable",
            "certificate_verify_failed",
            "ssl",
        )
    ):
        return ProviderIssue(
            "connection",
            f"暂时无法验证 {provider_label}：网络连接失败。你可以稍后重试，或先保存后继续。",
        )

    if any(
        kw in low
        for kw in (
            "model not found",
            "model_not_found",
            "does not exist",
            "unsupported parameter",
            "max_completion_tokens",
            "max_tokens",
        )
    ):
        return ProviderIssue(
            "model",
            f"{provider_label} 已连通，但 {model_label} 当前不可用或参数不兼容。你可以先保存 key，再切换模型。",
        )

    if len(msg) > 180:
        msg = msg[:180] + "..."
    return ProviderIssue("unknown", msg or "Unknown error")


def is_blocking_credential_error(error: Exception) -> bool:
    """Return True when the user should be prompted to reconfigure credentials."""
    return classify_provider_error(error).category in {"missing_key", "auth"}


def find_vote_blocking_issues(vote_result: dict) -> list[VoteProviderIssue]:
    """Extract vote providers that failed due to missing/invalid credentials."""
    issues: list[VoteProviderIssue] = []
    for entry in vote_result.get("individual_results", []):
        raw_error = entry.get("error")
        if not raw_error:
            continue
        provider = entry.get("provider", "")
        model = entry.get("model", "")
        issue = classify_provider_error(
            Exception(raw_error),
            provider=provider,
            model=model,
        )
        if issue.category in {"missing_key", "auth"}:
            issues.append(
                VoteProviderIssue(
                    provider=provider,
                    model=model,
                    raw_error=raw_error,
                    issue=issue,
                )
            )
    return issues


def replace_vote_provider(
    providers: list[str],
    old_provider: str,
    new_provider: str,
) -> list[str]:
    """Replace one vote provider while preserving order and removing duplicates."""
    replaced = False
    updated: list[str] = []
    for provider in providers:
        value = provider
        if not replaced and provider == old_provider:
            value = new_provider
            replaced = True
        if value not in updated:
            updated.append(value)
    if not replaced and new_provider not in updated:
        updated.append(new_provider)
    return updated


def validate_provider_credentials(
    provider: str,
    api_key: str,
    model: str | None = None,
) -> None:
    """Make a minimal live API call to verify the credential."""
    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS))
        raise RuntimeError(f"不支持的 provider: {provider}\n支持: {available}")

    cfg = PROVIDERS[provider]
    actual_model = model or cfg["default_model"]
    system_prompt = "Reply with OK."
    user_content = "ok"

    if cfg["type"] == "anthropic":
        _call_anthropic(
            system_prompt=system_prompt,
            user_content=user_content,
            api_key=api_key,
            model=actual_model,
            max_tokens=8,
        )
        return

    _call_openai_compat(
        system_prompt=system_prompt,
        user_content=user_content,
        api_key=api_key,
        model=actual_model,
        base_url=cfg["base_url"],
        max_tokens=8,
    )


def can_prompt_for_credentials(format_mode: str = "terminal") -> bool:
    """Interactive CLI prompts are only safe on a real terminal."""
    return (
        format_mode == "terminal"
        and sys.stdin.isatty()
        and sys.stdout.isatty()
    )


def prompt_configure_credentials(
    provider_hint: str | None = None,
    *,
    reason: str | None = None,
) -> tuple[str, str] | None:
    """Interactive CLI flow inspired by OpenCode's provider connect UX."""
    init_lang()

    provider = _resolve_provider_choice(provider_hint)
    if not provider:
        return None

    if reason:
        print(reason, file=sys.stderr)

    while True:
        configured = " (saved)" if get_api_key(provider) else ""
        print(
            f"\n{t('pick_provider')} {provider} "
            f"({PROVIDERS[provider]['default_model']}){configured}"
        )
        key = getpass.getpass(f"{provider} API key: ").strip()
        if not key:
            print("取消配置。", file=sys.stderr)
            return None

        print(f"验证 {provider} API key...", file=sys.stderr)

        try:
            validate_provider_credentials(provider, key)
        except Exception as exc:
            issue = classify_provider_error(
                exc,
                provider=provider,
                model=PROVIDERS[provider]["default_model"],
            )
            print(f"错误: {issue.message}", file=sys.stderr)

            if issue.category in {"auth", "missing_key"}:
                action = _prompt_recovery_action()
                if action == "retry":
                    continue
                if action == "switch":
                    provider = _resolve_provider_choice(None)
                    if not provider:
                        return None
                    continue
                return None

            if _confirm_yes("当前无法完全验证这个 key，仍然保存并继续？[y/N]: "):
                save_api_key(provider, key)
                print(
                    f"已保存 {provider} ({mask_key(key)})。分析时会再次尝试。",
                    file=sys.stderr,
                )
                return provider, key
            return None

        save_api_key(provider, key)
        print(t("key_saved", provider=provider, masked_key=mask_key(key)), file=sys.stderr)
        return provider, key


def _resolve_provider_choice(provider_hint: str | None) -> str | None:
    """Prompt for a provider when none was explicitly chosen."""
    if provider_hint and provider_hint in PROVIDERS:
        return provider_hint

    print(t("pick_provider"), file=sys.stderr)
    for index, name in enumerate(_PROVIDER_ORDER, 1):
        model = PROVIDERS[name]["default_model"]
        saved = " [saved]" if get_api_key(name) else ""
        print(f"  {index}. {name} ({model}){saved}", file=sys.stderr)

    while True:
        choice = input("> ").strip().lower()
        if not choice:
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(_PROVIDER_ORDER):
                return _PROVIDER_ORDER[idx]
        if choice in PROVIDERS:
            return choice
        print(t("invalid_choice", n=len(_PROVIDER_ORDER)), file=sys.stderr)


def _prompt_recovery_action() -> str:
    """Prompt for retry / switch / cancel after a bad key."""
    while True:
        choice = input("选择 [R] 重试当前 Provider / [S] 切换 Provider / [C] 取消: ").strip().lower()
        if choice in ("", "r", "retry"):
            return "retry"
        if choice in ("s", "switch"):
            return "switch"
        if choice in ("c", "cancel", "q", "quit"):
            return "cancel"


def _confirm_yes(prompt: str) -> bool:
    """Small yes/no helper for CLI recovery."""
    return input(prompt).strip().lower() in {"y", "yes"}
