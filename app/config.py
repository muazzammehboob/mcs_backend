"""Application configuration."""

from pydantic_settings import BaseSettings


import os

class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # On Vercel, use /tmp/mcs.db to persist state per-instance (mitigates multi-worker data loss).
    # Locally, use a local file for persistence.
    database_url: str = "sqlite+aiosqlite:////tmp/mcs.db" if os.getenv("VERCEL") else "sqlite+aiosqlite:///mcs.db"

    # Comma-separated list of allowed CORS origins.
    # Set MCS_ALLOWED_ORIGINS in the Vercel dashboard to include your frontend domain.
    # Example: "https://mcs-frontend.vercel.app,http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    class Config:
        env_prefix = "MCS_"


settings = Settings()
