"""SQLAlchemy ORM models for MCS.

Implements consolidated spec §19 (Data Model — Full Delta Summary).
Milestone 0 establishes the complete baseline schema including the two
additive tables (Attachment, GlobalSettings) identified during planning.
"""

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Project(Base):
    """A project is the top-level container for branches, nodes, and conversations."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Consolidated spec §9 — per-project persona/instructions override (nullable = inherit from global)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Consolidated spec §17 — per-project Gemini safety threshold config
    safety_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Model defaults
    default_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="gemini")
    default_model: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-2.5-flash")
    custom_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    branches: Mapped[list["Branch"]] = relationship(
        "Branch", back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    nodes: Mapped[list["Node"]] = relationship(
        "Node", back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    graph_layout_positions: Mapped[list["GraphLayoutPosition"]] = relationship(
        "GraphLayoutPosition", back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Branch(Base):
    """A branch is a linear sequence of prompt/response pairs within a project."""

    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
    parent_pr_pair_id: Mapped[int | None] = mapped_column(
        ForeignKey("pr_pairs.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standard"
    )  # 'standard' or 'temporary'
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Consolidated spec §8.1 — token meter static-context cache
    cached_static_token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Consolidated spec §12 — Summary Node linkage (nullable until M4, added now for schema completeness)
    linked_summary_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True
    )
    summary_cutoff_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="branches")
    children: Mapped[list["Branch"]] = relationship(
        "Branch",
        cascade="all, delete-orphan",
        back_populates="parent",
        passive_deletes=True
    )
    parent: Mapped["Branch | None"] = relationship(
        "Branch",
        remote_side="[Branch.id]",
        back_populates="children"
    )
    pr_pairs: Mapped[list["PRPair"]] = relationship(
        "PRPair",
        back_populates="branch",
        cascade="all, delete-orphan",
        order_by="PRPair.created_at",
        foreign_keys="PRPair.branch_id",
        passive_deletes=True
    )


class PRPair(Base):
    """A Prompt/Response pair represents one complete turn in a conversation branch.

    A PRPair only exists once it has both a prompt and a completed response.
    A pending/in-flight turn is never written as a row.
    """

    __tablename__ = "pr_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=False
    )
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Consolidated spec §10 — per-turn generation parameters actually used
    generation_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    branch: Mapped["Branch"] = relationship(
        "Branch", back_populates="pr_pairs", foreign_keys="[PRPair.branch_id]"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="pr_pair", cascade="all, delete-orphan", passive_deletes=True
    )


class Node(Base):
    """A Node is a reusable, @mentionable content block within a project.

    type: 'manual' (user-created) or 'summary' (AI-generated).
    """

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )  # 'manual' or 'summary'
    version_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="nodes")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_node_name_per_project"),
    )


class GraphLayoutPosition(Base):
    """Purely cosmetic 3D coordinates for Eagle View display.

    Zero effect on lineage or token accounting per consolidated spec.
    """

    __tablename__ = "graph_layout_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    branch_id: Mapped[int | None] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"), nullable=True
    )
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=True
    )
    x: Mapped[float] = mapped_column(nullable=False, default=0.0)
    y: Mapped[float] = mapped_column(nullable=False, default=0.0)
    z: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="graph_layout_positions")


class Attachment(Base):
    """A file attachment to a PRPair.

    Consolidated spec §13 — multimodal file support.
    """

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    pair_id: Mapped[int | None] = mapped_column(
        ForeignKey("pr_pairs.id", ondelete="CASCADE"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="attachments")
    pr_pair: Mapped["PRPair"] = relationship("PRPair", back_populates="attachments")


class GlobalSettings(Base):
    """Singleton table for global persona/instructions defaults.

    Consolidated spec §9 — global persona tier.
    Enforced at the service layer: exactly one row with id=1.
    """

    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
