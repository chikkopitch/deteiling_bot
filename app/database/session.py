"""Async SQLAlchemy engine, session factory, and health check."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseConfiguration(Protocol):
    database_url: str


@dataclass(slots=True)
class Database:
    """Own the SQLAlchemy engine and its AsyncSession factory."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def check_connection(self) -> None:
        """Execute a minimal PostgreSQL query or propagate the driver error."""
        async with self.engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            if result.scalar_one() != 1:
                raise RuntimeError("PostgreSQL health check returned an invalid result")

    async def dispose(self) -> None:
        """Close every pooled PostgreSQL connection owned by this process."""
        await self.engine.dispose()


def create_database(settings: DatabaseConfiguration) -> Database:
    """Create the async engine and reusable AsyncSession factory."""
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=False,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
    return Database(engine=engine, session_factory=session_factory)
