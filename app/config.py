"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # In-memory SQLite: works out of the box on Vercel serverless (no disk writes).
    # For local dev with persistence, override with:
    #   MCS_DATABASE_URL=sqlite+aiosqlite:///./mcs.db
    database_url: str = "sqlite+aiosqlite:///:memory:"

    # Comma-separated list of allowed CORS origins.
    # Set MCS_ALLOWED_ORIGINS in the Vercel dashboard to include your frontend domain.
    # Example: "https://mcs-frontend.vercel.app,http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    class Config:
        env_prefix = "MCS_"


settings = Settings()
