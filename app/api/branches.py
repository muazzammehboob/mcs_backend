"""Branch CRUD API — fork, label, delete, counts.

Implements consolidated spec §1 (v1 bug fix: actions scoped to completed Pair).
M2-T1 acceptance criteria: fork-from-Pair, branch-count-per-Pair, move-to-parent-pair.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.db.models import Branch as BranchModel, PRPair as PRPairModel
from app.schemas.branch import (
    BranchResponse,
    BranchForkRequest,
    BranchCountsResponse,
    MoveToParentPairResponse,
    LineageResponse,
    BranchUpdateRequest,
)
from app.domain.lineage import assemble_lineage
from app.schemas.lineage import LineageBranch, LineagePair
from app.deps import get_gemini_api_key, get_gemini_api_key_optional
from app.providers.gemini import GeminiProvider
from app.providers.fireworks import FireworksProvider
from app.providers.claude_provider import ClaudeProvider
from app.providers.base import Message
from app.schemas.chat import SendMessageRequest, SendMessageResponse
from app.providers.exceptions import GeminiAPIError, GeminiSafetyBlockError
from app.db.models import Attachment as AttachmentModel
from app.db.models import Project as ProjectModel
from app.db.models import Node as NodeModel

router = APIRouter(prefix="/branches", tags=["branches"])


def _branch_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")


def _pair_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRPair not found")


def _pair_not_completed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Cannot act on a PRPair with a pending/null response",
    )


@router.post("/{pr_pair_id}/fork", response_model=BranchResponse, status_code=status.HTTP_201_CREATED)
async def fork_branch(
    pr_pair_id: int,
    body: BranchForkRequest,
    db: AsyncSession = Depends(get_db),
) -> BranchModel:
    """Fork a new branch from a completed PRPair.

    The pr_pair_id in the URL is the fork point. The request body may
    contain an optional label. Returns 409 if the pair has no response.
    """
    # Verify the pair exists and is completed (eagerly load branch)
    result = await db.execute(
        select(PRPairModel)
        .where(PRPairModel.id == pr_pair_id)
        .options(selectinload(PRPairModel.branch))
    )
    pair = result.scalar_one_or_none()
    if pair is None:
        raise _pair_not_found()
    if pair.response_text is None:
        raise _pair_not_completed()

    # Create the new branch
    new_branch = BranchModel(
        project_id=pair.branch.project_id,
        parent_branch_id=pair.branch_id,
        parent_pr_pair_id=pr_pair_id,
        type="standard",
        label=body.label,
    )
    db.add(new_branch)
    await db.commit()
    await db.refresh(new_branch)
    return new_branch


@router.get("/{branch_id}/counts", response_model=BranchCountsResponse)
async def branch_counts(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return branch-count-per-pair for all pairs in a branch.

    Single aggregate query — no N+1 pattern.
    """
    # Verify branch exists
    result = await db.execute(
        select(BranchModel).where(BranchModel.id == branch_id)
    )
    branch = result.scalar_one_or_none()
    if branch is None:
        raise _branch_not_found()

    # Single aggregate query
    stmt = (
        select(BranchModel.parent_pr_pair_id, func.count(BranchModel.id))
        .where(BranchModel.parent_branch_id == branch_id)
        .group_by(BranchModel.parent_pr_pair_id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    counts = {str(row[0]): row[1] for row in rows if row[0] is not None}
    return {"counts": counts}


@router.get("/{branch_id}/move-to-parent-pair", response_model=MoveToParentPairResponse)
async def move_to_parent_pair(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the PRPair this branch was forked from, or null for Root."""
    result = await db.execute(
        select(BranchModel).where(BranchModel.id == branch_id)
    )
    branch = result.scalar_one_or_none()
    if branch is None:
        raise _branch_not_found()

    return {"parent_pr_pair_id": branch.parent_pr_pair_id}


@router.delete("/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a branch by ID."""
    result = await db.execute(select(BranchModel).where(BranchModel.id == branch_id))
    branch = result.scalar_one_or_none()
    if branch is None:
        raise _branch_not_found()

    await db.delete(branch)
    await db.commit()
    return None


@router.put("/{branch_id}", response_model=BranchResponse)
async def update_branch(
    branch_id: int,
    body: BranchUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> BranchModel:
    """Update/rename a branch's label."""
    result = await db.execute(
        select(BranchModel).where(BranchModel.id == branch_id)
    )
    branch = result.scalar_one_or_none()
    if branch is None:
        raise _branch_not_found()

    branch.label = body.label
    await db.commit()
    await db.refresh(branch)
    return branch


async def compute_branch_static_token_count(
    branch_id: int,
    db: AsyncSession,
    api_key: str | None = None,
) -> int:
    """Compute the static token count of the lineage context of a branch.

    If api_key is present, calls the LLM's countTokens API.
    If api_key is absent, falls back to character heuristic.
    """
    # Fetch branch
    result = await db.execute(select(BranchModel).where(BranchModel.id == branch_id))
    branch = result.scalar_one_or_none()
    if not branch:
        raise _branch_not_found()

    # Load project
    project_res = await db.execute(select(ProjectModel).where(ProjectModel.id == branch.project_id))
    project = project_res.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch all branches and completed pairs for the project
    branches_res = await db.execute(select(BranchModel).where(BranchModel.project_id == project.id))
    all_branches = branches_res.scalars().all()

    pairs_res = await db.execute(
        select(PRPairModel).join(BranchModel, PRPairModel.branch_id == BranchModel.id).where(BranchModel.project_id == project.id)
    )
    all_pairs = pairs_res.scalars().all()

    domain_branches = [
        LineageBranch(
            id=b.id, project_id=b.project_id, parent_branch_id=b.parent_branch_id,
            parent_pr_pair_id=b.parent_pr_pair_id, type=b.type, label=b.label,
            cached_static_token_count=b.cached_static_token_count,
            linked_summary_node_id=b.linked_summary_node_id,
            summary_cutoff_position=b.summary_cutoff_position, created_at=b.created_at
        ) for b in all_branches
    ]
    domain_pairs = [
        LineagePair(
            id=p.id, branch_id=p.branch_id, prompt_text=p.prompt_text,
            response_text=p.response_text, generation_params=p.generation_params,
            created_at=p.created_at
        ) for p in all_pairs if p.response_text is not None
    ]

    target_domain_branch = next((b for b in domain_branches if b.id == branch_id), None)
    if target_domain_branch is None:
        raise _branch_not_found()
    lineage_pairs = assemble_lineage(target_domain_branch, domain_pairs, domain_branches)

    # Compile system prompt
    system_parts = []
    if project.persona:
        system_parts.append(project.persona)
    if project.instructions:
        system_parts.append(project.instructions)
    if project.negative_constraints:
        system_parts.append(project.negative_constraints)

    if branch.linked_summary_node_id is not None:
        summary_res = await db.execute(select(NodeModel).where(NodeModel.id == branch.linked_summary_node_id))
        summary_node = summary_res.scalar_one_or_none()
        if summary_node:
            system_parts.append(f"Summary of previous conversation:\n{summary_node.content}")

    if branch.summary_cutoff_position is not None:
        lineage_pairs = lineage_pairs[branch.summary_cutoff_position:]

    system_prompt = "\n\n".join(system_parts) if system_parts else ""

    messages = []
    for pair in lineage_pairs:
        messages.append(Message(role="user", content=pair.prompt_text))
        messages.append(Message(role="assistant", content=pair.response_text))

    if api_key:
        requested_model = project.default_model or "gemini-2.5-flash"
        if requested_model and "claude" in requested_model.lower():
            provider = ClaudeProvider(api_key=api_key)
        else:
            provider = GeminiProvider(api_key=api_key)

        try:
            token_count = await provider.count_tokens(system_prompt, messages)
            return token_count
        except Exception as e:
            logger.warning(f"Error counting tokens via provider: {e}. Falling back to heuristic.")
        finally:
            await provider.close()

    # Heuristic fallback (character based)
    total_chars = len(system_prompt) + sum(len(m.content) for m in messages)
    return total_chars // 4


@router.get("/{branch_id}/lineage", response_model=LineageResponse)
async def get_branch_lineage(
    branch_id: int,
    api_key: str | None = Depends(get_gemini_api_key_optional),
    db: AsyncSession = Depends(get_db),
):
    """Get the full assembled lineage for a branch."""
    result = await db.execute(select(BranchModel).where(BranchModel.id == branch_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise _branch_not_found()

    # Calculate token count if it is None in database
    if target.cached_static_token_count is None:
        token_count = await compute_branch_static_token_count(
            branch_id=branch_id,
            db=db,
            api_key=api_key,
        )
        if api_key:
            target.cached_static_token_count = token_count
            await db.commit()
            await db.refresh(target)
    else:
        token_count = target.cached_static_token_count

    project_id = target.project_id

    branches_res = await db.execute(select(BranchModel).where(BranchModel.project_id == project_id))
    all_branches = branches_res.scalars().all()

    pairs_res = await db.execute(
        select(PRPairModel).join(BranchModel, PRPairModel.branch_id == BranchModel.id).where(BranchModel.project_id == project_id)
    )
    all_pairs = pairs_res.scalars().all()

    domain_branches = [
        LineageBranch(
            id=b.id, project_id=b.project_id, parent_branch_id=b.parent_branch_id,
            parent_pr_pair_id=b.parent_pr_pair_id, type=b.type, label=b.label,
            cached_static_token_count=b.cached_static_token_count,
            linked_summary_node_id=b.linked_summary_node_id,
            summary_cutoff_position=b.summary_cutoff_position, created_at=b.created_at
        ) for b in all_branches
    ]
    domain_pairs = [
        LineagePair(
            id=p.id, branch_id=p.branch_id, prompt_text=p.prompt_text,
            response_text=p.response_text, generation_params=p.generation_params,
            created_at=p.created_at
        ) for p in all_pairs if p.response_text is not None
    ]

    target_domain_branch = next((b for b in domain_branches if b.id == branch_id), None)
    if target_domain_branch is None:
        raise _branch_not_found()
    lineage_pairs = assemble_lineage(target_domain_branch, domain_pairs, domain_branches)

    return LineageResponse(
        pairs=[
            {
                "id": p.id,
                "branch_id": p.branch_id,
                "prompt_text": p.prompt_text,
                "response_text": p.response_text,
                "generation_params": p.generation_params,
                "created_at": p.created_at
            }
            for p in lineage_pairs
        ],
        linked_summary_node_id=target.linked_summary_node_id,
        summary_cutoff_position=target.summary_cutoff_position,
        cached_static_token_count=token_count,
    )



@router.post("/{branch_id}/messages")
async def send_message(
    branch_id: int,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message on a branch, appending a new PRPair to it via streaming."""
    api_key = body.api_key
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required api_key in request body",
        )
    # 1. Load branch and project
    result = await db.execute(
        select(BranchModel)
        .where(BranchModel.id == branch_id)
        .options(selectinload(BranchModel.project))
    )
    branch = result.scalar_one_or_none()
    if not branch:
        raise _branch_not_found()
    
    project = branch.project

    # 2. Get lineage pairs
    branches_res = await db.execute(select(BranchModel).where(BranchModel.project_id == project.id))
    all_branches = branches_res.scalars().all()
    pairs_res = await db.execute(
        select(PRPairModel).join(BranchModel, PRPairModel.branch_id == BranchModel.id).where(BranchModel.project_id == project.id)
    )
    all_pairs = pairs_res.scalars().all()

    domain_branches = [
        LineageBranch(
            id=b.id, project_id=b.project_id, parent_branch_id=b.parent_branch_id,
            parent_pr_pair_id=b.parent_pr_pair_id, type=b.type, label=b.label,
            cached_static_token_count=b.cached_static_token_count,
            linked_summary_node_id=b.linked_summary_node_id,
            summary_cutoff_position=b.summary_cutoff_position, created_at=b.created_at
        ) for b in all_branches
    ]
    domain_pairs = [
        LineagePair(
            id=p.id, branch_id=p.branch_id, prompt_text=p.prompt_text,
            response_text=p.response_text, generation_params=p.generation_params,
            created_at=p.created_at
        ) for p in all_pairs if p.response_text is not None
    ]
    
    target_domain_branch = next((b for b in domain_branches if b.id == branch_id), None)
    if target_domain_branch is None:
        raise _branch_not_found()
    lineage_pairs = assemble_lineage(target_domain_branch, domain_pairs, domain_branches)

    # 3. Build system prompt
    system_parts = []
    if project.persona:
        system_parts.append(project.persona)
    if project.instructions:
        system_parts.append(project.instructions)
    if project.negative_constraints:
        system_parts.append(project.negative_constraints)
    
    if branch.linked_summary_node_id is not None:
        summary_res = await db.execute(select(NodeModel).where(NodeModel.id == branch.linked_summary_node_id))
        summary_node = summary_res.scalar_one_or_none()
        if summary_node:
            system_parts.append(f"Summary of previous conversation:\n{summary_node.content}")
            
    if branch.summary_cutoff_position is not None:
        lineage_pairs = lineage_pairs[branch.summary_cutoff_position:]

    messages = []
    for pair in lineage_pairs:
        messages.append(Message(role="user", content=pair.prompt_text))
        messages.append(Message(role="assistant", content=pair.response_text))
    
    messages.append(Message(role="user", content=body.prompt_text))

    async def event_generator():
        system_prompt = "\n\n".join(system_parts) if system_parts else ""
        requested_model = body.model or project.default_model or "gemini-2.5-flash"
        
        # Primary provider selection
        if body.provider == "fireworks":
            primary_provider_class = FireworksProvider
        elif requested_model and "claude" in requested_model.lower():
            primary_provider_class = ClaudeProvider
        else:
            primary_provider_class = GeminiProvider

        provider = primary_provider_class(api_key=api_key)
        
        accumulated_content = ""
        usage_data = {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0}
        
        try:
            # Try to fetch using primary provider
            stream = provider.chat_completion_stream(
                system=system_prompt,
                messages=messages,
                model=requested_model,
                temperature=body.temperature,
                top_p=body.top_p,
                max_output_tokens=body.max_output_tokens,
                effort=body.effort,
            )
            
            fallback_needed = False
            first_event = None
            
            try:
                # Retrieve first event to see if it immediately fails or errors out
                first_event = await anext(stream)
            except Exception as e:
                logger.error(f"Primary provider failed immediately: {e}. Attempting fallback.")
                fallback_needed = True
                
            if first_event and first_event.get("type") == "error":
                if first_event.get("error_type") == "safety_block":
                    yield f"data: {json.dumps(first_event)}\n\n"
                    await provider.close()
                    return
                logger.error(f"Primary provider returned error: {first_event}. Attempting fallback.")
                fallback_needed = True

            if fallback_needed:
                await provider.close()
                if body.provider == "fireworks":
                    fallback_provider_class = FireworksProvider
                    fallback_model = "accounts/fireworks/models/llama-v3p1-8b-instruct"
                else:
                    fallback_provider_class = GeminiProvider
                    fallback_model = "gemini-2.5-flash"
                
                provider = fallback_provider_class(api_key=api_key)
                requested_model = fallback_model
                stream = provider.chat_completion_stream(
                    system=system_prompt,
                    messages=messages,
                    model=fallback_model,
                    temperature=body.temperature,
                    top_p=body.top_p,
                    max_output_tokens=body.max_output_tokens,
                    effort=body.effort,
                )
                first_event = await anext(stream)

            # Consume the stream
            current_event = first_event
            while current_event is not None:
                if current_event["type"] == "token":
                    accumulated_content += current_event["content"]
                    yield f"data: {json.dumps({'type': 'token', 'content': current_event['content']})}\n\n"
                elif current_event["type"] == "usage":
                    usage_data = {
                        "promptTokenCount": current_event["usage"]["prompt_tokens"],
                        "candidatesTokenCount": current_event["usage"]["completion_tokens"],
                        "totalTokenCount": current_event["usage"]["total_tokens"],
                    }
                elif current_event["type"] == "error":
                    yield f"data: {json.dumps(current_event)}\n\n"
                    await provider.close()
                    return
                
                try:
                    current_event = await anext(stream)
                except StopAsyncIteration:
                    current_event = None

            await provider.close()

            if not accumulated_content.strip():
                yield f"data: {json.dumps({'type': 'error', 'message': 'No content generated.'})}\n\n"
                return

            # Save PRPair
            new_pair = PRPairModel(
                branch_id=branch_id,
                prompt_text=body.prompt_text,
                response_text=accumulated_content,
                generation_params={
                    "model": requested_model,
                    "temperature": body.temperature,
                    "top_p": body.top_p,
                    "max_output_tokens": body.max_output_tokens,
                    "effort": body.effort
                }
            )
            db.add(new_pair)
            await db.flush()

            # Link attachments
            if body.attachment_ids:
                for att_id in body.attachment_ids:
                    att_res = await db.execute(select(AttachmentModel).where(AttachmentModel.id == att_id))
                    att = att_res.scalar_one_or_none()
                    if att:
                        att.pair_id = new_pair.id

            # Update branch static token count
            if usage_data and usage_data.get("totalTokenCount"):
                branch.cached_static_token_count = usage_data["totalTokenCount"]
            else:
                branch.cached_static_token_count = None

            await db.commit()
            await db.refresh(new_pair)


            # Emit done event
            done_payload = {
                "type": "done",
                "node_id": new_pair.id,
                "full_content": accumulated_content,
                "created_at": new_pair.created_at.isoformat() if new_pair.created_at else None,
                "usage": usage_data
            }
            yield f"data: {json.dumps(done_payload)}\n\n"

        except asyncio.CancelledError:
            await db.rollback()
            await provider.close()
            raise
        except Exception as exc:
            await db.rollback()
            await provider.close()
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
