"""Database session management.

Implements consolidated spec §4 (Locked Technical Stack — SQLAlchemy 2.0 async + aiosqlite).

`engine` is exported so that the application lifespan hook in main.py can call
`Base.metadata.create_all(engine)` to initialise the in-memory schema on cold start.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import settings
from sqlalchemy.pool import StaticPool

engine_kwargs = {"echo": False}
if ":memory:" in settings.database_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool

# Exported so lifespan in main.py can call create_all on this engine.
engine = create_async_engine(settings.database_url, **engine_kwargs)

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
