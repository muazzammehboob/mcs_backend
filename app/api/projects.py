"""Project CRUD + auto-create Root Branch.

Implements consolidated spec §19 (Project/Branch auto-creation).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import Project, Branch
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.branch import BranchResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/branches", response_model=list[BranchResponse])
async def list_project_branches(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[Branch]:
    """List all branches belonging to a project.

    Used by the frontend to bootstrap the branch-tree sidebar on project load.
    Returns branches ordered by creation time so the root branch comes first.
    """
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    result = await db.execute(
        select(Branch)
        .where(Branch.project_id == project_id)
        .order_by(Branch.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Create a Project and auto-create its Root Branch in one transaction.

    Implements consolidated spec §19: the Root Branch has parent_branch_id=NULL,
    parent_pr_pair_id=NULL, and type='standard'.
    """
    project = Project(
        name=body.name,
        default_provider=body.default_provider,
        default_model=body.default_model,
        custom_base_url=body.custom_base_url,
        token_limit=body.token_limit,
        persona=body.persona,
        instructions=body.instructions,
        negative_constraints=body.negative_constraints,
        safety_settings=body.safety_settings,
    )
    db.add(project)
    await db.flush()  # flush to get project.id

    root_branch = Branch(
        project_id=project.id,
        parent_branch_id=None,
        parent_pr_pair_id=None,
        type="standard",
        label=None,
    )
    db.add(root_branch)

    await db.commit()
    await db.refresh(project)
    return project


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """Get a single project by ID."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    result = await db.execute(select(Project))
    return result.scalars().all()


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.default_provider is not None:
        project.default_provider = body.default_provider
    if body.default_model is not None:
        project.default_model = body.default_model
    if body.custom_base_url is not None:
        project.custom_base_url = body.custom_base_url
    if body.token_limit is not None:
        project.token_limit = body.token_limit
    if body.persona is not None:
        project.persona = body.persona
    if body.instructions is not None:
        project.instructions = body.instructions
    if body.negative_constraints is not None:
        project.negative_constraints = body.negative_constraints
    if body.safety_settings is not None:
        project.safety_settings = body.safety_settings

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a project."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await db.delete(project)
    await db.commit()
    return None
