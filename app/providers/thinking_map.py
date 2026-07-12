"""Model-family-aware effort/thinking parameter mapping.

Implements consolidated spec §11 (Effort / Reasoning Dial).

Gemini has two incompatible mechanisms depending on model generation:
  - Gemini 2.5-series: thinking_config.thinking_budget (int)
  - Gemini 3.x-series: thinking_config.thinking_level (enum string)

Sending both in the same request is a 400 error. This module provides a
lookup table and mapping function to ensure exactly one param (or none) is sent.
"""

from __future__ import annotations

from typing import TypedDict


class _ThinkingSpec(TypedDict):
    param: str  # "thinking_budget" or "thinking_level"
    values: dict[str, int | str]  # effort level -> provider value


# Static lookup: model name pattern -> thinking spec
# Patterns are checked in order; first match wins.
_THINKING_MAP: list[tuple[str, _ThinkingSpec]] = [
    # Gemini 3.x series (Flash family: 4 levels; Pro family: 2 levels)
    (
        "gemini-3",
        {
            "param": "thinkingLevel",
            "values": {
                "low": "MINIMAL",
                "medium": "LOW",
                "high": "MEDIUM",
                "max": "HIGH",
            },
        },
    ),
    # Gemini 2.5 series (token budget)
    (
        "gemini-2.5",
        {
            "param": "thinkingBudget",
            "values": {
                "low": 0,
                "medium": -1,  # dynamic
                "high": 8192,
                "max": 24576,
            },
        },
    ),
]

# Models with no thinking support at all
_NON_THINKING_PATTERNS: list[str] = [
    "gemini-1",
    "gemini-embedding",
    "gemini-pro-vision",
]


def get_thinking_config(
    model_name: str,
    effort_level: str,
) -> dict[str, dict[str, int | str]] | None:
    """Return the thinking_config dict for a given model and effort level.

    Args:
        model_name: The Gemini model name (e.g., "gemini-2.5-flash").
        effort_level: One of "low", "medium", "high", "max".

    Returns:
        A dict like {"thinking_config": {"thinking_budget": 8192}} or
        {"thinking_config": {"thinking_level": "MEDIUM"}}, or None if the
        model has no thinking support.

    Raises:
        ValueError: If effort_level is not one of the four valid levels.
    """
    if effort_level not in {"low", "medium", "high", "max"}:
        raise ValueError(
            f"Invalid effort_level: {effort_level!r}. "
            "Must be one of: low, medium, high, max"
        )

    # Check non-thinking models first
    lower = model_name.lower()
    for pat in _NON_THINKING_PATTERNS:
        if pat in lower:
            return None

    # Find the first matching pattern
    for pat, spec in _THINKING_MAP:
        if pat in lower:
            provider_value = spec["values"][effort_level]
            return {"thinkingConfig": {spec["param"]: provider_value}}

    # Unknown model — default to no thinking config (safe fallback)
    return None


def get_supported_effort_levels(model_name: str) -> list[str] | None:
    """Return the supported effort levels for a model, or None if no thinking support."""
    lower = model_name.lower()
    for pat in _NON_THINKING_PATTERNS:
        if pat in lower:
            return None

    for pat, spec in _THINKING_MAP:
        if pat in lower:
            return list(spec["values"].keys())

    return None
