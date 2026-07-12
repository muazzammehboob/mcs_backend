"""TokenEstimator — pure domain service.

Implements consolidated spec §8 (Token Estimation Strategy).

Split output:
  - static_context_tokens: from Branch.cached_static_token_count (exact/cached)
  - live_input_tokens: heuristic computed client-side per §8.2

The stale-cache trigger cases (§8.1):
  1. First-ever view of a branch with no sends yet (cache is null).
  2. Summary state changes on the branch.

This module contains zero FastAPI imports and zero SQLAlchemy Session imports.
"""

from __future__ import annotations

from collections.abc import Callable

from app.schemas.lineage import LineageBranch


def get_static_token_count(
    branch: LineageBranch,
    token_counter: Callable[[], int] | None = None,
    summary_state_changed: bool = False,
) -> int | None:
    """Return the static context token count for a branch.

    Implements consolidated spec §8.1:
      - Returns the cached value directly when it exists and no Summary state
        has changed since caching.
      - Triggers exactly one call to the injected token_counter when the cache
        is null (fresh branch) or when summary_state_changed is True.

    Args:
        branch: The branch whose token count is needed.
        token_counter: A callable that computes the exact token count.
            Required when cache is null or summary_state_changed is True.
        summary_state_changed: True if a Summary was applied, disconnected,
            or deleted since the last cache. Forces a refresh.

    Returns:
        The static context token count, or None if it could not be determined.
    """
    if branch.cached_static_token_count is not None and not summary_state_changed:
        return branch.cached_static_token_count

    if token_counter is None:
        return None

    return token_counter()


def refresh_cache(
    branch: LineageBranch,
    token_counter: Callable[[], int],
) -> int:
    """Force a cache refresh by calling the token counter.

    Returns the new count. Caller is responsible for persisting the new
    value to Branch.cached_static_token_count.

    Args:
        branch: The branch to refresh (used for context; not mutated).
        token_counter: Callable that computes the exact token count.

    Returns:
        The freshly computed token count.
    """
    return token_counter()
