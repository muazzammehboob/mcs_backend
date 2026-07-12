"""Tests for the effort/thinking parameter mapping.

Implements consolidated spec §11 and M3-T1 acceptance criteria.
"""

import pytest

from app.providers.thinking_map import get_thinking_config


class Test25Series:
    """Gemini 2.5-series uses thinking_budget (int)."""

    def test_25_flash_uses_budget_not_level(self) -> None:
        """A 2.5-series model uses thinking_budget in the request body.

        M3-T1 acceptance criterion:
        A call against a 2.5-series model name uses thinking_budget,
        never thinking_level.
        """
        result = get_thinking_config("gemini-2.5-flash", "high")
        assert result is not None
        assert "thinkingConfig" in result
        assert "thinkingBudget" in result["thinkingConfig"]
        assert "thinkingLevel" not in result["thinkingConfig"]

    def test_25_budget_values(self) -> None:
        """Verify specific budget values for each effort level."""
        assert get_thinking_config("gemini-2.5-flash", "low") == {"thinkingConfig": {"thinkingBudget": 0}}
        assert get_thinking_config("gemini-2.5-flash", "medium") == {"thinkingConfig": {"thinkingBudget": -1}}
        assert get_thinking_config("gemini-2.5-flash", "high") == {"thinkingConfig": {"thinkingBudget": 8192}}
        assert get_thinking_config("gemini-2.5-flash", "max") == {"thinkingConfig": {"thinkingBudget": 24576}}


class Test3xSeries:
    """Gemini 3.x-series uses thinking_level (enum string)."""

    def test_3x_uses_level_not_budget(self) -> None:
        """A 3.x-series model uses thinking_level, never thinking_budget.

        M3-T1 acceptance criterion:
        A call against a 3.x-series model name uses thinking_level,
        never thinking_budget.
        """
        result = get_thinking_config("gemini-3-flash", "high")
        assert result is not None
        assert "thinkingConfig" in result
        assert "thinkingLevel" in result["thinkingConfig"]
        assert "thinkingBudget" not in result["thinkingConfig"]

    def test_3x_level_values(self) -> None:
        """Verify specific level enum values for each effort level."""
        assert get_thinking_config("gemini-3-flash", "low") == {"thinkingConfig": {"thinkingLevel": "MINIMAL"}}
        assert get_thinking_config("gemini-3-flash", "medium") == {"thinkingConfig": {"thinkingLevel": "LOW"}}
        assert get_thinking_config("gemini-3-flash", "high") == {"thinkingConfig": {"thinkingLevel": "MEDIUM"}}
        assert get_thinking_config("gemini-3-flash", "max") == {"thinkingConfig": {"thinkingLevel": "HIGH"}}


class TestNonThinkingModel:
    """Non-thinking models omit thinking_config entirely."""

    def test_non_thinking_omits_config(self) -> None:
        """A model with no thinking support produces no thinking_config key.

        M3-T1 acceptance criterion:
        A model with no thinking support in the capability table produces
        a request body with no thinking_config key at all.
        """
        result = get_thinking_config("gemini-1.5-flash", "high")
        assert result is None


class TestInvalidEffort:
    """Invalid effort level raises ValueError."""

    def test_invalid_effort_raises(self) -> None:
        with pytest.raises(ValueError):
            get_thinking_config("gemini-2.5-flash", "invalid")
