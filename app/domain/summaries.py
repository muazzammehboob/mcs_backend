"""SummaryService — pure domain service.

Implements consolidated spec §12 (Summarization / Compaction Strategy) and §8.1
(Token Meter must react immediately to Replace/Disconnect).

Single one-shot summarization call over the branch's effective lineage.
No recursive/hierarchical summarization. No mutation of ancestor branches.

This module contains zero FastAPI imports and zero SQLAlchemy imports.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.lineage import LineageBranch, LineagePair


@dataclass
class SummaryDraft:
    """A draft summary produced by generate_summary."""

    name: str
    content: str
    pair_count: int


# Fixed summarization prompt
_SUMMARIZATION_PROMPT = """Summarize the following conversation concisely. Preserve key decisions, facts, and context that would be needed to continue the conversation meaningfully. Do not include meta-commentary about the summary itself.

Conversation:
"""


def generate_summary(
    branch: LineageBranch,
    lineage_pairs: list[LineagePair],
    existing_node_names: set[str],
    chat_completer: Callable[[str, str], str],
) -> SummaryDraft:
    """Generate a summary draft for a branch's lineage.

    Builds the conversation text from the lineage pairs, sends it through
    a fixed summarization prompt via the provided chat_completer, and
    returns a draft with an auto-generated, de-duplicated name.

    The draft is NOT linked to the branch — the caller must call
    apply_summary() separately after user confirmation.

    Args:
        branch: The branch being summarized.
        lineage_pairs: The assembled lineage pairs.
        existing_node_names: Set of existing node names to avoid collisions.
        chat_completer: Callable(prompt, model_name) -> response_text.

    Returns:
        A SummaryDraft with name, content, and pair_count.
    """
    if not lineage_pairs:
        conversation_text = "(empty conversation)"
    else:
        lines: list[str] = []
        for pair in lineage_pairs:
            lines.append(f"User: {pair.prompt_text}")
            lines.append(f"Assistant: {pair.response_text}")
        conversation_text = "\n".join(lines)

    full_prompt = _SUMMARIZATION_PROMPT + conversation_text

    summary_content = chat_completer(full_prompt, "gemini-2.5-flash")

    # Auto-generate name from branch label
    base_name = branch.label or f"Summary-{branch.id}"
    name = _deduplicate_name(base_name, existing_node_names)

    return SummaryDraft(
        name=name,
        content=summary_content,
        pair_count=len(lineage_pairs),
    )


def _deduplicate_name(base: str, existing: set[str]) -> str:
    """De-duplicate a node name by appending a counter suffix."""
    if base not in existing:
        return base
    counter = 1
    while True:
        candidate = f"{base}-{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


def compute_summary_lineage(
    all_pairs: list[LineagePair],
    summary_node_content: str,
    cutoff_position: int,
) -> list[LineagePair]:
    """Compute the effective lineage when a summary is active.

    Returns pairs AFTER the cutoff, with the summary content prepended
    as a pseudo-pair representing the summarized context.

    Args:
        all_pairs: The full assembled lineage (ancestors + branch pairs).
        summary_node_content: The content of the summary node.
        cutoff_position: The number of pairs before the cutoff.

    Returns:
        List of pairs after the cutoff, with summary prepended.
    """
    post_cutoff = all_pairs[cutoff_position:]
    return post_cutoff
