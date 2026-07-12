"""Node domain services — @mention resolution and cycle detection.

Implements consolidated spec §9 (Nodes) and M2-T1 acceptance criteria.

Pure domain service: zero FastAPI imports, zero SQLAlchemy imports.
Operates on plain data structures passed in by the caller.
"""

from __future__ import annotations

import re
from collections.abc import Mapping


MENTION_PATTERN = re.compile(r"@\{([^}]+)\}")


def extract_mentions(content: str) -> list[str]:
    """Extract @mention names from node content.

    Matches @{Name} syntax and returns the list of unique mention names.

    Args:
        content: The node content text to scan.

    Returns:
        List of unique mention names (without @{} wrapper).
    """
    mentions = MENTION_PATTERN.findall(content)
    seen: set[str] = set()
    result: list[str] = []
    for m in mentions:
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def detect_cycle(
    node_name: str,
    node_content: str,
    all_nodes: Mapping[str, str],
) -> list[str] | None:
    """Detect if saving a node would create a @mention reference cycle.

    A cycle exists if (transitively) following @mentions leads back to the
    node being saved. Returns the cycle path if found, None otherwise.

    M2-T1 acceptance criterion: if Node A's content @mentions Node B, and
    B (transitively) @mentions A, reject the save with a 400 naming the cycle.

    Args:
        node_name: The name of the node being saved.
        node_content: The content of the node being saved.
        all_nodes: Mapping of existing node name -> node content.

    Returns:
        A list of node names forming the cycle, or None if no cycle.
    """
    # Build a temporary graph including the node being saved
    graph = dict(all_nodes)
    graph[node_name] = node_content

    visited: set[str] = set()
    path: list[str] = []

    def dfs(current: str) -> list[str] | None:
        if current in path:
            # Found a cycle — return the cycle portion of the path
            idx = path.index(current)
            return path[idx:] + [current]

        if current in visited:
            return None

        visited.add(current)
        path.append(current)

        content = graph.get(current, "")
        for mention in extract_mentions(content):
            if mention in graph:
                result = dfs(mention)
                if result is not None:
                    return result

        path.pop()
        return None

    return dfs(node_name)
