import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.database.connection import create_database_engine
from app.database.session import create_session_factory, session_scope


async def test_session_scope_rolls_back_on_exception(
    test_settings: Settings,
) -> None:
    engine = create_database_engine(test_settings)
    session_factory = create_session_factory(engine)

    try:
        async with session_scope(session_factory) as session:
            await session.execute(
                text(
                    "CREATE TEMPORARY TABLE phase_1_3_session_probe "
                    "(value integer NOT NULL) ON COMMIT PRESERVE ROWS"
                )
            )
            await session.execute(
                text("INSERT INTO phase_1_3_session_probe (value) VALUES (1)")
            )
            await session.commit()

        with pytest.raises(RuntimeError, match="force rollback"):
            async with session_scope(session_factory) as session:
                await session.execute(
                    text("INSERT INTO phase_1_3_session_probe (value) VALUES (2)")
                )
                raise RuntimeError("force rollback")

        async with session_scope(session_factory) as session:
            row_count = await session.scalar(
                text("SELECT count(*) FROM phase_1_3_session_probe")
            )
            assert row_count == 1
    finally:
        await engine.dispose()
