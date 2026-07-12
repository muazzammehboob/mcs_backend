"""Tests for LineageAssembler.

Implements consolidated spec §4.5 and M1-T1 acceptance criteria.
"""

import pytest
from datetime import datetime

from app.schemas.lineage import LineageBranch, LineagePair
from app.domain.lineage import assemble_lineage


def _pair(id_: int, branch_id: int, prompt: str = "", response: str = "") -> LineagePair:
    """Helper to build a LineagePair."""
    return LineagePair(
        id=id_,
        branch_id=branch_id,
        prompt_text=prompt or f"prompt-{id_}",
        response_text=response or f"response-{id_}",
        created_at=datetime(2024, 1, id_, 12, 0, 0),
    )


def _branch(
    id_: int,
    parent_branch_id: int | None = None,
    parent_pr_pair_id: int | None = None,
    type_: str = "standard",
) -> LineageBranch:
    """Helper to build a LineageBranch."""
    return LineageBranch(
        id=id_,
        project_id=1,
        parent_branch_id=parent_branch_id,
        parent_pr_pair_id=parent_pr_pair_id,
        type=type_,
    )


class TestForkSiblingExclusion:
    """The critical test: fork/sibling exclusion per M1-T1 acceptance criterion."""

    def test_auth_forked_after_b2_excludes_b3(self) -> None:
        """Auth(forked after B2) lineage == [R1,R2,B1,B2]; B3 absent.

        M1-T1 acceptance criterion (literal):
        Root(R1,R2) -> Backend(B1,B2,B3) -> Auth(forked after B2)
        Auth's assembled lineage == [R1,R2,B1,B2] and B3 is absent.
        """
        # Root branch
        root = _branch(id_=1)
        # Backend branch, forked from Root after R2
        backend = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=2)
        # Auth branch, forked from Backend after B2
        auth = _branch(id_=3, parent_branch_id=2, parent_pr_pair_id=4)

        # Pairs
        r1 = _pair(1, 1, "R1-prompt", "R1-response")
        r2 = _pair(2, 1, "R2-prompt", "R2-response")
        b1 = _pair(3, 2, "B1-prompt", "B1-response")
        b2 = _pair(4, 2, "B2-prompt", "B2-response")
        b3 = _pair(5, 2, "B3-prompt", "B3-response")

        all_pairs = [r1, r2, b1, b2, b3]
        all_branches = [root, backend, auth]

        lineage = assemble_lineage(auth, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        assert lineage_ids == [1, 2, 3, 4], (
            f"Expected [R1,R2,B1,B2] = [1,2,3,4], got {lineage_ids}"
        )
        assert 5 not in lineage_ids, "B3 must NOT appear in Auth's lineage"


class TestEmptyAncestorContribution:
    """A branch forked from Root before any Pair exists."""

    def test_fork_before_any_pair(self) -> None:
        """Fork before any pair: empty ancestor contribution, no error.

        M1-T1 acceptance criterion:
        A branch forked from Root before any Pair exists produces an empty
        ancestor contribution (parent_pr_pair_id=None handled without error).
        """
        root = _branch(id_=1)
        # Forked from Root before any pairs exist
        early_fork = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=None)

        # No pairs on root yet
        all_pairs: list[LineagePair] = []
        all_branches = [root, early_fork]

        lineage = assemble_lineage(early_fork, all_pairs, all_branches)
        assert lineage == []

    def test_fork_with_pairs_on_target(self) -> None:
        """Fork before any pair, then target branch gets its own pairs."""
        root = _branch(id_=1)
        early_fork = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=None)

        f1 = _pair(10, 2, "F1-prompt", "F1-response")

        all_pairs = [f1]
        all_branches = [root, early_fork]

        lineage = assemble_lineage(early_fork, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]
        assert lineage_ids == [10]  # Only F1, no ancestors


class TestThreeLevelDeepFork:
    """3-level-deep fork chain with correct ordering and no cross-sibling leakage."""

    def test_three_level_fork(self) -> None:
        """Root -> A -> B -> C, each forked at a different mid-branch point.

        M1-T1 acceptance criterion:
        A 3-level-deep fork chain produces the correct concatenated,
        correctly-ordered list with no duplicate Pairs and no cross-sibling
        leakage at any level.
        """
        # Root: R1, R2, R3
        root = _branch(id_=1)
        # A: forked from Root after R2
        branch_a = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=2)
        # B: forked from A after A1
        branch_b = _branch(id_=3, parent_branch_id=2, parent_pr_pair_id=4)
        # C: forked from B after B2
        branch_c = _branch(id_=4, parent_branch_id=3, parent_pr_pair_id=7)

        # Pairs
        r1 = _pair(1, 1)  # Root
        r2 = _pair(2, 1)  # Root
        r3 = _pair(3, 1)  # Root — sibling, NOT in A's lineage

        a1 = _pair(4, 2)  # Branch A
        a2 = _pair(5, 2)  # Branch A — sibling, NOT in B's lineage

        b1 = _pair(6, 3)  # Branch B
        b2 = _pair(7, 3)  # Branch B — sibling, NOT in C's lineage

        c1 = _pair(8, 4)  # Branch C

        all_pairs = [r1, r2, r3, a1, a2, b1, b2, c1]
        all_branches = [root, branch_a, branch_b, branch_c]

        lineage = assemble_lineage(branch_c, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        # C's lineage: ancestors up to B2 + C's own pairs
        # Root: [R1, R2] (up to R2, fork point for A)
        # A: [A1] (up to A1, fork point for B)
        # B: [B1, B2] (up to B2, fork point for C)
        # C: [C1]
        expected = [1, 2, 4, 6, 7, 8]
        assert lineage_ids == expected, f"Expected {expected}, got {lineage_ids}"

        # Verify no cross-sibling leakage
        assert 3 not in lineage_ids, "R3 (sibling on Root) must not leak"
        assert 5 not in lineage_ids, "A2 (sibling on A) must not leak"
        assert 8 in lineage_ids, "C1 must be included"


class TestTargetBranchOwnPairs:
    """Target branch's own pairs are included in lineage."""

    def test_target_pairs_included(self) -> None:
        """Pairs on the target branch itself are appended after ancestors."""
        root = _branch(id_=1)
        child = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=1)

        r1 = _pair(1, 1)
        c1 = _pair(2, 2)
        c2 = _pair(3, 2)

        all_pairs = [r1, c1, c2]
        all_branches = [root, child]

        lineage = assemble_lineage(child, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        assert lineage_ids == [1, 2, 3], f"Expected [1,2,3], got {lineage_ids}"


class TestNoDuplicates:
    """No duplicate pairs appear in lineage."""

    def test_no_duplicate_pairs(self) -> None:
        """A pair should never appear twice in the lineage."""
        root = _branch(id_=1)
        child = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=2)

        r1 = _pair(1, 1)
        r2 = _pair(2, 1)
        c1 = _pair(3, 2)

        all_pairs = [r1, r2, c1]
        all_branches = [root, child]

        lineage = assemble_lineage(child, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        assert len(lineage_ids) == len(set(lineage_ids)), "No duplicates allowed"


class TestResponsePrecondition:
    """Pairs without response_text should never appear."""

    def test_pair_without_response_raises(self) -> None:
        """A pair with null response triggers AssertionError."""
        root = _branch(id_=1)
        bad_pair = LineagePair(id=1, branch_id=1, prompt_text="hi", response_text=None)  # type: ignore[arg-type]

        all_pairs = [bad_pair]
        all_branches = [root]

        with pytest.raises(AssertionError):
            assemble_lineage(root, all_pairs, all_branches)
