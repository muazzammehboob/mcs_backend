"""Database session management.

Implements consolidated spec §4 (Locked Technical Stack — SQLAlchemy 2.0 async + aiosqlite).
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for FastAPI dependency injection."""
    async with async_session() as session:
        yield session
