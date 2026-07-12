"""Tests for SummaryService domain logic.

Implements M4-T1 acceptance criteria.
"""

import pytest
from datetime import datetime

from app.schemas.lineage import LineageBranch, LineagePair
from app.domain.summaries import generate_summary, compute_summary_lineage, _deduplicate_name


def _pair(id_: int, branch_id: int, prompt: str = "", response: str = "") -> LineagePair:
    return LineagePair(
        id=id_,
        branch_id=branch_id,
        prompt_text=prompt or f"prompt-{id_}",
        response_text=response or f"response-{id_}",
        created_at=datetime(2024, 1, id_, 12, 0, 0),
    )


def _branch(id_: int, label: str | None = None) -> LineageBranch:
    return LineageBranch(
        id=id_,
        project_id=1,
        label=label,
    )


class TestGenerateSummary:
    """Test summary generation."""

    def test_generate_produces_draft(self) -> None:
        """Generate produces a SummaryDraft with name and content."""
        branch = _branch(id_=1, label="Backend")
        pairs = [_pair(i, 1) for i in range(1, 4)]

        def fake_completer(prompt: str, model: str) -> str:
            return "Summary of the conversation."

        draft = generate_summary(branch, pairs, set(), fake_completer)

        assert draft.name == "Backend"
        assert draft.content == "Summary of the conversation."
        assert draft.pair_count == 3

    def test_name_deduplication(self) -> None:
        """Name is de-duplicated against existing node names."""
        branch = _branch(id_=1, label="Backend")
        pairs = [_pair(1, 1)]

        def fake_completer(prompt: str, model: str) -> str:
            return "Summary"

        draft = generate_summary(branch, pairs, {"Backend", "Backend-1"}, fake_completer)
        assert draft.name == "Backend-2"


class TestDeduplicateName:
    """Test the name deduplication helper."""

    def test_no_collision(self) -> None:
        assert _deduplicate_name("Foo", {"Bar"}) == "Foo"

    def test_single_collision(self) -> None:
        assert _deduplicate_name("Foo", {"Foo"}) == "Foo-1"

    def test_multiple_collisions(self) -> None:
        assert _deduplicate_name("Foo", {"Foo", "Foo-1", "Foo-2"}) == "Foo-3"


class TestComputeSummaryLineage:
    """Test the summary lineage computation."""

    def test_post_cutoff_pairs(self) -> None:
        """compute_summary_lineage returns pairs after the cutoff."""
        pairs = [_pair(i, 1) for i in range(1, 11)]
        result = compute_summary_lineage(pairs, "summary content", 6)
        # Pairs 7-10 should remain
        assert len(result) == 4
        assert result[0].id == 7
        assert result[-1].id == 10

    def test_cutoff_at_zero(self) -> None:
        """Cutoff at 0 means all pairs are after the cutoff."""
        pairs = [_pair(i, 1) for i in range(1, 4)]
        result = compute_summary_lineage(pairs, "summary", 0)
        assert len(result) == 3
