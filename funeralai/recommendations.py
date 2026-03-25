"""Canonical recommendation labels and compatibility helpers."""

from __future__ import annotations

from typing import Literal


RECOMMENDATION_POSITIVE = "整挺好"
RECOMMENDATION_NEGATIVE = "吹牛逼呢"
RECOMMENDATION_NEUTRAL = "整不明白"
DEFAULT_RECOMMENDATION = RECOMMENDATION_NEUTRAL

_LEGACY_ALIASES = {
    "值得进一步看": RECOMMENDATION_POSITIVE,
    "暂不建议投资": RECOMMENDATION_NEGATIVE,
    "信息不足，不能判断": RECOMMENDATION_NEUTRAL,
    "牛逼": RECOMMENDATION_POSITIVE,
    "傻逼": RECOMMENDATION_NEGATIVE,
    "吹牛逼": RECOMMENDATION_NEGATIVE,
}


def normalize_recommendation(value: str | None) -> str:
    """Return the canonical recommendation label."""
    if not value:
        return DEFAULT_RECOMMENDATION

    text = value.strip()
    if text in (RECOMMENDATION_POSITIVE, RECOMMENDATION_NEGATIVE, RECOMMENDATION_NEUTRAL):
        return text
    if text in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[text]
    return text


def recommendation_bucket(
    value: str | None,
) -> Literal["positive", "negative", "neutral"]:
    """Classify a recommendation into its presentation bucket."""
    normalized = normalize_recommendation(value)
    if normalized == RECOMMENDATION_POSITIVE:
        return "positive"
    if normalized == RECOMMENDATION_NEGATIVE:
        return "negative"
    return "neutral"
