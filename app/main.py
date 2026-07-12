"""FastAPI application entry point.

Implements consolidated spec §4 (Locked Technical Stack — FastAPI + Uvicorn).

Vercel deployment notes
-----------------------
* ``lifespan`` runs create_all on every cold start so the in-memory SQLite DB
  is always fully initialised.  It also ensures the GlobalSettings singleton
  row (id=1) exists.  Both operations are idempotent.
* Migrations (Alembic) are NOT run here — they are a local-dev / CI concern.
* CORS origins are read from ``MCS_ALLOWED_ORIGINS`` env var so the Vercel
  dashboard can be used to add the deployed frontend URL without a redeploy.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.api import (
    attachments,
    branches,
    chat,
    graph,
    health,
    models_catalog,
    nodes,
    pairs,
    projects,
    summaries,
    settings as settings_router,
)
from app.config import settings
from app.db.models import Base, GlobalSettings
from app.db.session import engine, async_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise DB schema and seed required rows.

    Runs once per cold start.  Safe to call concurrently — create_all and the
    GlobalSettings upsert are both idempotent.
    """
    # Create all tables (no-op if they already exist, which can't happen with
    # in-memory SQLite but guards against future driver changes).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed GlobalSettings singleton row (id=1) if absent.
    async with async_session() as session:
        result = await session.execute(select(GlobalSettings).where(GlobalSettings.id == 1))
        if result.scalar_one_or_none() is None:
            session.add(GlobalSettings(id=1, persona=None, instructions=None, negative_constraints=None))
            await session.commit()

    yield
    # Shutdown: nothing to clean up for in-memory SQLite.


# Parse CORS origins from the comma-separated env var.
_origins_str = getattr(settings, "allowed_origins", None) or "*"
_allowed_origins = [o.strip() for o in _origins_str.split(",") if o.strip()]

app = FastAPI(title="MCS Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(branches.router)
app.include_router(pairs.router)
app.include_router(nodes.router)
app.include_router(chat.router)
app.include_router(models_catalog.router)
app.include_router(attachments.router)
app.include_router(summaries.router)
app.include_router(graph.router)
app.include_router(settings_router.router)


# Stub endpoint protected by BYOK for acceptance criterion proof
from app.deps import get_gemini_api_key

@app.get("/protected-stub")
async def protected_stub(api_key: str = Depends(get_gemini_api_key)) -> dict[str, str]:
    """Test endpoint to prove get_gemini_api_key() dependency works.

    Milestone 0 acceptance criterion: an endpoint protected by
    get_gemini_api_key() returns 401 when the header is absent and
    passes the key through when present.
    """
    return {"received_key": api_key}


# Note: protected_stub will be removed in later milestones; it exists
# solely to satisfy the acceptance criterion about the BYOK dependency.
