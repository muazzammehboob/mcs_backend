"""Vercel Python serverless function entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI `app` (or `handler`)
object in `api/index.py`.  This thin wrapper re-exports the real FastAPI
app so the DDD structure in `app/` is unchanged.
"""

import asyncio
from sqlalchemy import select

from app.main import app  # noqa: F401 -- re-exported for Vercel runtime
from app.db.session import engine, async_session
from app.db.models import Base, GlobalSettings

async def _init_db():
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed GlobalSettings singleton row (id=1) if absent.
    async with async_session() as session:
        result = await session.execute(select(GlobalSettings).where(GlobalSettings.id == 1))
        if result.scalar_one_or_none() is None:
            session.add(GlobalSettings(id=1, persona=None, instructions=None, negative_constraints=None))
            await session.commit()

def sync_init_db():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(_init_db())
    else:
        asyncio.run(_init_db())

# Run synchronously at module load time for Vercel cold starts.
# This ensures in-memory DB is initialized because Vercel doesn't trigger ASGI lifespan events properly.
sync_init_db()
