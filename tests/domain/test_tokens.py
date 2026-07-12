"""Tests for TokenEstimator.

Implements consolidated spec §8 and M1-T1 acceptance criteria.
"""

from datetime import datetime

import pytest

from app.schemas.lineage import LineageBranch
from app.domain.tokens import get_static_token_count, refresh_cache


def _branch(cached_count: int | None = None) -> LineageBranch:
    """Helper to build a LineageBranch with optional cached token count."""
    return LineageBranch(
        id=1,
        project_id=1,
        cached_static_token_count=cached_count,
    )


class TestCachedValue:
    """TokenEstimator returns cached value directly when cache is non-null."""

    def test_returns_cached_without_calling_counter(self) -> None:
        """When cache is non-null, the token counter is never called.

        M1-T1 acceptance criterion:
        TokenEstimator returns cached Branch.cached_static_token_count directly
        with zero calls to the injected token-counter when the cache is non-null
        and no Summary state has changed since caching.
        """
        branch = _branch(cached_count=1500)
        call_count = 0

        def counter() -> int:
            nonlocal call_count
            call_count += 1
            return 9999

        result = get_static_token_count(branch, token_counter=counter)
        assert result == 1500
        assert call_count == 0, "Counter must not be called when cache exists"


class TestNullCache:
    """TokenEstimator triggers one call when cache is null."""

    def test_triggers_one_call_when_cache_null(self) -> None:
        """When cache is null, exactly one call to the counter is made.

        M1-T1 acceptance criterion:
        TokenEstimator triggers exactly one call to the injected token-counter
        callable when cache is null (fresh branch, no sends yet).
        """
        branch = _branch(cached_count=None)
        call_count = 0

        def counter() -> int:
            nonlocal call_count
            call_count += 1
            return 2500

        result = get_static_token_count(branch, token_counter=counter)
        assert result == 2500
        assert call_count == 1, "Exactly one counter call expected"


class TestSummaryStateChanged:
    """TokenEstimator refreshes when summary state changes."""

    def test_refreshes_when_summary_state_changed(self) -> None:
        """When summary_state_changed=True, cache is bypassed.

        Consolidated spec §8.1: Token Meter must visibly react to
        Replace/Disconnect immediately, not on next send.
        """
        branch = _branch(cached_count=1500)
        call_count = 0

        def counter() -> int:
            nonlocal call_count
            call_count += 1
            return 800  # Summary reduces token count

        result = get_static_token_count(
            branch, token_counter=counter, summary_state_changed=True
        )
        assert result == 800
        assert call_count == 1, "Counter must be called when summary state changes"


class TestNoCounterProvided:
    """When no counter is provided and cache can't be used."""

    def test_returns_none_when_no_counter_and_null_cache(self) -> None:
        """Returns None if cache is null and no counter provided."""
        branch = _branch(cached_count=None)
        result = get_static_token_count(branch, token_counter=None)
        assert result is None


class TestRefreshCache:
    """Force refresh via refresh_cache()."""

    def test_refresh_cache_calls_counter(self) -> None:
        """refresh_cache always calls the counter."""
        branch = _branch(cached_count=1500)
        call_count = 0

        def counter() -> int:
            nonlocal call_count
            call_count += 1
            return 3000

        result = refresh_cache(branch, counter)
        assert result == 3000
        assert call_count == 1
