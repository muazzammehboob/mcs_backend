"""Shared test fixtures."""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.db.models import Base
from app.main import app

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

test_async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables from the metadata (Alembic-free for tests)."""
    async with test_engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)


from sqlalchemy import text

async def drop_db() -> None:
    """Drop all tables."""
    async with test_engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=OFF"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("PRAGMA foreign_keys=ON"))


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async DB session with tables created."""
    await init_db()
    async with test_async_session() as session:
        yield session
        await session.rollback()
    await drop_db()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an async HTTP client."""
    await init_db()
    # Monkey-patch the app's DB session to use our test session
    from app.db import session as session_module
    original_session = session_module.async_session
    session_module.async_session = test_async_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    session_module.async_session = original_session
    await drop_db()
