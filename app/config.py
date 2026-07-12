"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    database_url: str = "sqlite+aiosqlite:///./mcs.db"

    class Config:
        env_prefix = "MCS_"


settings = Settings()
