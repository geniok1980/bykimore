from typing import Any, AsyncGenerator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

async_engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "sqlite+aiosqlite:///"),
    pool_pre_ping=True,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI, 
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def get_db() -> AsyncGenerator[AsyncSession | Any, Any]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# Ensure SQLite enforces foreign key constraints (required for ON DELETE CASCADE)
# This needs to be enabled per-connection.
if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    # For the synchronous engine
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma_sync(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # For the async engine (use the underlying sync engine)
    @event.listens_for(async_engine.sync_engine, "connect")
    def _set_sqlite_pragma_async(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
