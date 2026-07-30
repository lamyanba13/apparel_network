from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.database.connection import create_database_engine
from app.database.health import check_database_connection
from app.database.session import create_session_factory


async def test_async_database_engine_connects(test_settings: Settings) -> None:
    engine = create_database_engine(test_settings)
    try:
        assert await check_database_connection(engine) is True
    finally:
        await engine.dispose()


async def test_session_factory_creates_async_session(
    test_settings: Settings,
) -> None:
    engine = create_database_engine(test_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_factory() as session:
            assert isinstance(session, AsyncSession)
            assert session.bind is engine
    finally:
        await engine.dispose()
