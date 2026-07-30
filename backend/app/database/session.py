from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

SessionFactory = async_sessionmaker[AsyncSession]


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """Create the application session factory bound to one process engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


class DatabaseSessionManager:
    """Own the engine and request-session factory for one process."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.session_factory = create_session_factory(engine)

    async def close(self) -> None:
        """Release all pooled connections during graceful shutdown."""
        await self.engine.dispose()


@asynccontextmanager
async def session_scope(session_factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Yield one session and roll back failed work before closing it."""
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Inject one automatically closed database session per request."""
    manager = cast(DatabaseSessionManager, request.app.state.database)
    async with session_scope(manager.session_factory) as session:
        yield session
