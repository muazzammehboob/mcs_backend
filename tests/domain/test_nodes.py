"""Tests for Node domain services — @mention extraction and cycle detection.

Implements M2-T1 acceptance criteria.
"""

import pytest

from app.domain.nodes import extract_mentions, detect_cycle


class TestExtractMentions:
    """Test @mention extraction from node content."""

    def test_extract_single_mention(self) -> None:
        content = "Refer to @{Context} for more info"
        assert extract_mentions(content) == ["Context"]

    def test_extract_multiple_mentions(self) -> None:
        content = "See @{Foo} and @{Bar} and @{Baz}"
        assert extract_mentions(content) == ["Foo", "Bar", "Baz"]

    def test_no_mentions(self) -> None:
        content = "Plain text with no mentions"
        assert extract_mentions(content) == []

    def test_unique_mentions_only(self) -> None:
        content = "@{Dup} and @{Dup} again"
        assert extract_mentions(content) == ["Dup"]


class TestDetectCycle:
    """Test @mention cycle detection."""

    def test_no_cycle(self) -> None:
        """No cycle when A mentions B but B doesn't mention A."""
        all_nodes = {"B": "Content of B with no mentions"}
        result = detect_cycle("A", "See @{B}", all_nodes)
        assert result is None

    def test_direct_cycle(self) -> None:
        """Direct cycle: A mentions B, B mentions A."""
        all_nodes = {"B": "See @{A}"}
        result = detect_cycle("A", "See @{B}", all_nodes)
        assert result is not None
        assert "A" in result
        assert "B" in result

    def test_transitive_cycle(self) -> None:
        """Transitive cycle: A -> B -> C -> A."""
        all_nodes = {
            "B": "See @{C}",
            "C": "See @{A}",
        }
        result = detect_cycle("A", "See @{B}", all_nodes)
        assert result is not None
        assert result[0] == result[-1]  # cycle starts and ends with same node

    def test_no_cycle_mentions_nonexistent(self) -> None:
        """Mentioning a non-existent node doesn't create a cycle."""
        all_nodes: dict[str, str] = {}
        result = detect_cycle("A", "See @{Nonexistent}", all_nodes)
        assert result is None

    def test_self_mention(self) -> None:
        """A node mentioning itself is a cycle."""
        all_nodes: dict[str, str] = {}
        result = detect_cycle("A", "See @{A}", all_nodes)
        assert result is not None
        assert "A" in result

    def test_update_creates_cycle(self) -> None:
        """Editing B to mention A when A already mentions B creates a cycle."""
        all_nodes = {"A": "See @{B}"}
        result = detect_cycle("B", "See @{A}", all_nodes)
        assert result is not None
        assert result == ["B", "A", "B"]
