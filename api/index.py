"""Vercel Python serverless function entrypoint.

Vercel's Python runtime looks for an ASGI/WSGI `app` (or `handler`)
object in `api/index.py`.  This thin wrapper re-exports the real FastAPI
app so the DDD structure in `app/` is unchanged.

All routes are defined in `app/main.py`; this file must stay minimal.
"""

from app.main import app  # noqa: F401 -- re-exported for Vercel runtime
