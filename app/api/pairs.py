"""PRPair API.

M2-T1: endpoints for pair operations including the completed-Pair scoping rule.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.db.models import PRPair as PRPairModel
from app.schemas.pair import PRPairResponse

router = APIRouter(prefix="/pairs", tags=["pairs"])


@router.get("/{pair_id}", response_model=PRPairResponse)
async def get_pair(
    pair_id: int,
    db: AsyncSession = Depends(get_db),
) -> PRPairModel:
    """Get a single PRPair by ID."""
    result = await db.execute(
        select(PRPairModel).where(PRPairModel.id == pair_id)
    )
    pair = result.scalar_one_or_none()
    if pair is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pair not found")
    return pair
