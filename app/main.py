"""FastAPI application entry point.

Implements consolidated spec §4 (Locked Technical Stack — FastAPI + Uvicorn).
"""

from fastapi import Depends, FastAPI

from app.api import attachments, branches, chat, graph, health, models_catalog, nodes, pairs, projects, summaries, settings

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MCS Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
app.include_router(settings.router)


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
