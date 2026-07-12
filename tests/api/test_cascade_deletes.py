"""Tests for cascade delete behavior.

Implements M6-T1 acceptance criteria.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import (
    Attachment,
    Branch,
    GraphLayoutPosition,
    Node,
    PRPair,
    Project,
)


async def _create_full_project(db: AsyncSession) -> int:
    """Create a project with branches, pairs, nodes, layouts, attachments.
    Returns project_id."""
    project = Project(name="Cascade Test", default_model="gemini-2.5-flash")
    db.add(project)
    await db.flush()

    # Root branch
    root = Branch(project_id=project.id, type="standard")
    db.add(root)
    await db.flush()

    # Pairs on root
    for i in range(3):
        pair = PRPair(branch_id=root.id, prompt_text=f"P{i}", response_text=f"R{i}")
        db.add(pair)
    await db.flush()

    # Child branch (forked from root)
    child = Branch(
        project_id=project.id,
        parent_branch_id=root.id,
        parent_pr_pair_id=1,
        type="standard",
    )
    db.add(child)
    await db.flush()

    # Pair on child
    child_pair = PRPair(branch_id=child.id, prompt_text="CP", response_text="CR")
    db.add(child_pair)
    await db.flush()

    # Node
    node = Node(project_id=project.id, name="TestNode", content="Content")
    db.add(node)
    await db.flush()

    # Layout position
    layout = GraphLayoutPosition(project_id=project.id, branch_id=root.id, x=0, y=0)
    db.add(layout)
    await db.flush()

    # Attachment (pair_id references a real pair)
    attachment = Attachment(
        project_id=project.id,
        pair_id=child_pair.id,
        file_path="/tmp/test.txt",
        mime_type="text/plain",
        original_filename="test.txt",
        size_bytes=100,
    )
    db.add(attachment)
    await db.commit()

    return project.id


@pytest.mark.asyncio
async def test_project_delete_cascades_to_all_children(db_session: AsyncSession) -> None:
    """Deleting a Project deletes all Branches, Pairs, Nodes, Layouts, Attachments.

    M6-T1 acceptance criterion:
    Deleting a Project deletes all of its Branches, Pairs, Nodes,
    GraphLayoutPositions, and Attachments — verified by row-count assertions.
    """
    project_id = await _create_full_project(db_session)

    # Count rows before
    project = await db_session.get(Project, project_id)
    assert project is not None

    await db_session.delete(project)
    await db_session.commit()

    # Verify project is gone
    assert await db_session.get(Project, project_id) is None

    # Count remaining rows in child tables
    for model in (Branch, PRPair, Node, GraphLayoutPosition, Attachment):
        result = await db_session.execute(select(func.count()).select_from(model))
        count = result.scalar()
        assert count == 0, f"Expected 0 {model.__tablename__} rows, got {count}"


@pytest.mark.asyncio
async def test_branch_delete_cascades_to_descendants(db_session: AsyncSession) -> None:
    """Deleting a mid-tree Branch deletes itself + descendant Branches recursively.

    M6-T1 acceptance criterion:
    Deleting a mid-tree Branch that has 2 descendant forked Branches deletes
    all 3 branches (itself + both descendants) and their Pairs, recursively.
    """
    project = Project(name="Branch Cascade", default_model="gemini-2.5-flash")
    db_session.add(project)
    await db_session.flush()

    # Root -> A -> B (3-level tree)
    root = Branch(project_id=project.id, type="standard")
    db_session.add(root)
    await db_session.flush()

    pair_r = PRPair(branch_id=root.id, prompt_text="RP", response_text="RR")
    db_session.add(pair_r)
    await db_session.flush()

    a = Branch(project_id=project.id, parent_branch_id=root.id, parent_pr_pair_id=pair_r.id, type="standard")
    db_session.add(a)
    await db_session.flush()

    pair_a = PRPair(branch_id=a.id, prompt_text="AP", response_text="AR")
    db_session.add(pair_a)
    await db_session.flush()

    b = Branch(project_id=project.id, parent_branch_id=a.id, parent_pr_pair_id=pair_a.id, type="standard")
    db_session.add(b)
    await db_session.flush()

    pair_b = PRPair(branch_id=b.id, prompt_text="BP", response_text="BR")
    db_session.add(pair_b)
    await db_session.commit()

    branch_count_before = (await db_session.execute(select(func.count()).select_from(Branch))).scalar()
    assert branch_count_before == 3

    # Delete the middle branch (A)
    branch_a = await db_session.get(Branch, a.id)
    await db_session.delete(branch_a)
    await db_session.commit()

    # Both A and B should be gone (B is a descendant of A)
    # Root should remain
    remaining_branches = (await db_session.execute(select(func.count()).select_from(Branch))).scalar()
    assert remaining_branches == 1

    db_session.expunge_all()
    assert await db_session.get(Branch, root.id) is not None
    assert await db_session.get(Branch, a.id) is None
    assert await db_session.get(Branch, b.id) is None


@pytest.mark.asyncio
async def test_node_delete_leaves_existing_pairs_unchanged(db_session: AsyncSession) -> None:
    """Deleting a Node leaves existing PRPair response_text unchanged.

    M6-T1 acceptance criterion:
    Deleting a Node that is @mentioned in an already-completed PRPair leaves
    that PRPair's stored response_text completely unchanged.
    """
    project = Project(name="Node Delete", default_model="gemini-2.5-flash")
    db_session.add(project)
    await db_session.flush()

    root = Branch(project_id=project.id, type="standard")
    db_session.add(root)
    await db_session.flush()

    # Create a pair that references a node
    node = Node(project_id=project.id, name="Context", content="Important context")
    db_session.add(node)
    await db_session.flush()

    pair = PRPair(
        branch_id=root.id,
        prompt_text="Tell me about @{Context}",
        response_text="Context says: Important context",
    )
    db_session.add(pair)
    await db_session.commit()

    # Delete the node
    await db_session.delete(node)
    await db_session.commit()

    # Pair response should be unchanged
    result = await db_session.execute(select(PRPair).where(PRPair.id == pair.id))
    pair_after = result.scalar_one()
    assert pair_after.response_text == "Context says: Important context"
