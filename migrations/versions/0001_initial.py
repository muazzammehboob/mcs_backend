"""Initial schema — all 7 tables for Milestone 0.

Revision ID: 0001
Revises:
Create Date: 2026-07-06 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. global_settings — no foreign keys
    op.create_table(
        "global_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("negative_constraints", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. projects — no foreign keys
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("persona", sa.Text(), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("negative_constraints", sa.Text(), nullable=True),
        sa.Column("safety_settings", sa.JSON(), nullable=True),
        sa.Column("default_provider", sa.String(length=50), nullable=False),
        sa.Column("default_model", sa.String(length=100), nullable=False),
        sa.Column("custom_base_url", sa.String(length=500), nullable=True),
        sa.Column("token_limit", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. nodes — FK to projects only
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("version_counter", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_node_name_per_project"),
    )

    # 4. branches — FK to projects; deferred FKs to pr_pairs and nodes use use_alter
    op.create_table(
        "branches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("parent_pr_pair_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="standard"),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("cached_static_token_count", sa.Integer(), nullable=True),
        sa.Column("linked_summary_node_id", sa.Integer(), nullable=True),
        sa.Column("summary_cutoff_position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 5. pr_pairs — FK to branches
    op.create_table(
        "pr_pairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("generation_params", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 6. attachments — FK to projects and pr_pairs
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pair_id",
            sa.Integer(),
            sa.ForeignKey("pr_pairs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 7. graph_layout_positions — FK to projects, branches, nodes
    op.create_table(
        "graph_layout_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Integer(),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "node_id",
            sa.Integer(),
            sa.ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("x", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("z", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Deferred FKs on branches using batch_alter_table for SQLite compatibility
    with op.batch_alter_table("branches") as batch_op:
        batch_op.create_foreign_key(
            "fk_branches_parent_pr_pair",
            "pr_pairs",
            ["parent_pr_pair_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_branches_linked_summary_node",
            "nodes",
            ["linked_summary_node_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_table("graph_layout_positions")
    op.drop_table("attachments")
    op.drop_table("pr_pairs")
    op.drop_table("branches")
    op.drop_table("nodes")
    op.drop_table("projects")
    op.drop_table("global_settings")
