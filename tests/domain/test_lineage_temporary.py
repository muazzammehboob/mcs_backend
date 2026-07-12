"""Tests for Temporary Branch lineage assembly.

Implements M5-T1 acceptance criteria.
"""

from datetime import datetime

from app.schemas.lineage import LineageBranch, LineagePair
from app.domain.lineage import assemble_lineage


def _pair(id_: int, branch_id: int) -> LineagePair:
    return LineagePair(
        id=id_,
        branch_id=branch_id,
        prompt_text=f"prompt-{id_}",
        response_text=f"response-{id_}",
        created_at=datetime(2024, 1, id_, 12, 0, 0),
    )


def _branch(
    id_: int,
    parent_branch_id: int | None = None,
    parent_pr_pair_id: int | None = None,
    type_: str = "standard",
) -> LineageBranch:
    return LineageBranch(
        id=id_,
        project_id=1,
        parent_branch_id=parent_branch_id,
        parent_pr_pair_id=parent_pr_pair_id,
        type=type_,
    )


class TestTemporaryBranchLineage:
    """Temporary Branch own pairs are excluded from lineage."""

    def test_temporary_excludes_own_pairs(self) -> None:
        """3 sequential messages in a Temporary Branch produce independent assemblies.

        M5-T1 acceptance criterion:
        Sending 3 sequential messages within a single Temporary Branch produces
        3 independent lineage assemblies, each identical (same ancestor-chain
        content) except for the new prompt — none of the Temporary Branch's own
        prior 3 turns compound into later ones.
        """
        root = _branch(id_=1)
        temp = _branch(
            id_=2,
            parent_branch_id=1,
            parent_pr_pair_id=2,
            type_="temporary",
        )

        r1 = _pair(1, 1)
        r2 = _pair(2, 1)
        # Temporary branch has its own pairs
        t1 = _pair(3, 2)
        t2 = _pair(4, 2)
        t3 = _pair(5, 2)

        all_pairs = [r1, r2, t1, t2, t3]
        all_branches = [root, temp]

        # Lineage for the temporary branch should NOT include t1, t2, t3
        lineage = assemble_lineage(temp, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        # Only ancestor pairs (R1, R2) should be present
        assert lineage_ids == [1, 2], f"Expected [1, 2], got {lineage_ids}"
        assert 3 not in lineage_ids, "T1 must not appear in temporary lineage"
        assert 4 not in lineage_ids, "T2 must not appear in temporary lineage"
        assert 5 not in lineage_ids, "T3 must not appear in temporary lineage"

    def test_standard_includes_own_pairs(self) -> None:
        """A standard branch still includes its own pairs."""
        root = _branch(id_=1)
        child = _branch(id_=2, parent_branch_id=1, parent_pr_pair_id=2)

        r1 = _pair(1, 1)
        r2 = _pair(2, 1)
        c1 = _pair(3, 2)

        all_pairs = [r1, r2, c1]
        all_branches = [root, child]

        lineage = assemble_lineage(child, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]
        assert lineage_ids == [1, 2, 3]

    def test_fork_from_temporary_to_standard(self) -> None:
        """A fork from a Temporary Branch Pair to a new standard branch works.

        M5-T1 acceptance criterion:
        A fork from a mid-Temporary-Branch Pair to a new standard branch
        correctly includes the ancestor chain PLUS that Temporary Branch's
        Pairs up to the fork point.
        """
        root = _branch(id_=1)
        temp = _branch(
            id_=2,
            parent_branch_id=1,
            parent_pr_pair_id=2,
            type_="temporary",
        )
        # New standard branch forked from T2 on the temporary branch
        standard = _branch(id_=3, parent_branch_id=2, parent_pr_pair_id=4)

        r1 = _pair(1, 1)
        r2 = _pair(2, 1)
        t1 = _pair(3, 2)
        t2 = _pair(4, 2)

        all_pairs = [r1, r2, t1, t2]
        all_branches = [root, temp, standard]

        lineage = assemble_lineage(standard, all_pairs, all_branches)
        lineage_ids = [p.id for p in lineage]

        # Standard branch gets: ancestors (R1,R2) + temp pairs up to T2 (T1,T2)
        assert lineage_ids == [1, 2, 3, 4], f"Expected [1,2,3,4], got {lineage_ids}"
