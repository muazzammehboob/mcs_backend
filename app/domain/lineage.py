"""LineageAssembler — pure domain service.

Implements consolidated spec §4.5 (ancestor-chain walk with correct fork/sibling handling).

Given a target Branch, walks its ancestor chain and produces the exact ordered list
of Pairs that should be sent to the LLM as conversation history. Handles forking
and sibling-exclusion correctly: a Pair on an ancestor branch that was created AFTER
the fork point is NOT included in the forked branch's lineage.

This module contains zero FastAPI imports and zero SQLAlchemy Session imports —
it operates on plain dataclasses passed in by the caller.
"""

from __future__ import annotations

from app.schemas.lineage import LineageBranch, LineagePair


def assemble_lineage(
    target_branch: LineageBranch,
    all_pairs: list[LineagePair],
    all_branches: list[LineageBranch],
) -> list[LineagePair]:
    """Assemble the full conversation lineage for a target branch.

    The result includes:
      1. All ancestor pairs from the root down to the fork points, in order.
      2. All pairs on the target branch itself, in order.

    Siblings (Pairs on ancestor branches created after the fork point) are
    correctly excluded.

    Implements consolidated spec §4.5.

    Args:
        target_branch: The branch whose lineage is being assembled.
        all_pairs: All PRPairs in the project (flat list).
        all_branches: All Branches in the project (flat list).

    Returns:
        Ordered list of LineagePair from oldest to newest.

    Raises:
        AssertionError: If any pair in the lineage has a null response_text
            (structurally should never happen per M0 constraints).
    """
    branch_map = {b.id: b for b in all_branches}
    # Pairs per branch, sorted by created_at (chronological order)
    pairs_by_branch: dict[int, list[LineagePair]] = {}
    for p in all_pairs:
        pairs_by_branch.setdefault(p.branch_id, []).append(p)
    for branch_id in pairs_by_branch:
        pairs_by_branch[branch_id].sort(key=lambda pair: pair.created_at or pair.id)

    result: list[LineagePair] = []

    # --- Collect ancestor contributions ---
    ancestors = _collect_ancestor_contributions(
        target_branch, branch_map, pairs_by_branch
    )
    result.extend(ancestors)

    # --- Collect target branch's own pairs ---
    # M5-T1: Temporary Branches are stateless-within-themselves.
    # A Temporary Branch's own prior Pairs are excluded from its lineage.
    # The ancestor chain above the fork point is unaffected and still included.
    if target_branch.type != "temporary":
        own_pairs = pairs_by_branch.get(target_branch.id, [])
        result.extend(own_pairs)

    # --- Defensive assertion: every pair must have a response ---
    for pair in result:
        assert pair.response_text is not None, (
            f"Pair {pair.id} has no response_text — incomplete pairs "
            "must never appear in lineage"
        )

    return result


def _collect_ancestor_contributions(
    target_branch: LineageBranch,
    branch_map: dict[int, LineageBranch],
    pairs_by_branch: dict[int, list[LineagePair]],
) -> list[LineagePair]:
    """Walk the ancestor chain and collect pairs up to each fork point.

    Walks from the target branch up to the root. For each ancestor branch,
    includes only pairs up to (and including) the pair at which the child
    branch was forked. Reverses the result so pairs are in chronological
    order (root to target).

    Args:
        target_branch: The branch to start from (we walk UP from here).
        branch_map: Map of branch_id -> LineageBranch.
        pairs_by_branch: Map of branch_id -> sorted list of LineagePair.

    Returns:
        Ordered list of ancestor LineagePair from oldest to newest.
    """
    # Each segment is a list of pairs from one ancestor branch.
    # Collected in target-to-root order; reversed at the end.
    segments: list[list[LineagePair]] = []
    current = target_branch

    while current.parent_branch_id is not None:
        parent = branch_map[current.parent_branch_id]
        parent_pairs = pairs_by_branch.get(parent.id, [])

        # The cutoff is the pair on the parent at which 'current' was forked.
        cutoff = current.parent_pr_pair_id

        if cutoff is not None:
            included: list[LineagePair] = []
            for pair in parent_pairs:
                included.append(pair)
                if pair.id == cutoff:
                    break
            segments.append(included)
        # If cutoff is None, the child was forked before any pair existed
        # on the parent — the parent contributes nothing.

        current = parent

    # segments is in [target's parent, ..., root] order. Reverse to chronological.
    segments.reverse()

    result: list[LineagePair] = []
    for segment in segments:
        result.extend(segment)
    return result
