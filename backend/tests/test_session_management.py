from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from prometheus_client import generate_latest
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.config import get_settings
from app.common.events import DomainEvent
from app.core.config import Settings
from app.main import create_application
from app.modules.identity.application.schemas import (
    RefreshSessionCreate,
    UserCreate,
)
from app.modules.identity.application.session_management import (
    SessionCleanupService,
    SessionManagementService,
)
from app.modules.identity.domain import parse_device
from app.modules.identity.domain.session_events import (
    OtherSessionsRevoked,
    SessionCleanupCompleted,
    SessionRenamed,
    SessionRevoked,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyRefreshSessionRepository,
    SqlAlchemyUserRepository,
)
from app.observability.metrics import (
    SESSION_CLEANUP_EXECUTIONS,
    SESSION_REVOCATIONS,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"


@dataclass
class RecordingPublisher:
    events: list[DomainEvent] = field(default_factory=list)

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


@pytest.fixture
def migrated_database(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> Iterator[None]:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config(BACKEND_ROOT / "alembic.ini"), "head")
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def session_db(
    migrated_database: None,
    database_url: str,
) -> AsyncIterator[AsyncSession]:
    del migrated_database
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


async def _user(session: AsyncSession) -> UUID:
    record = await SqlAlchemyUserRepository(session).add(
        UserCreate(
            email="sessions@example.com",
            display_name="Session User",
            password_hash=PASSWORD_HASH,
        )
    )
    return record.id


async def _session(
    session: AsyncSession,
    user_id: UUID,
    *,
    token_marker: str,
    display_name: str,
    current: datetime,
    expires_at: datetime | None = None,
    revoked: bool = False,
    trusted: bool = False,
) -> UUID:
    record = await SqlAlchemyRefreshSessionRepository(session).add(
        RefreshSessionCreate(
            user_id=user_id,
            refresh_token_hash=token_marker * 64,
            family_id=UUID(int=ord(token_marker)),
            device_name=display_name,
            display_name=display_name,
            browser="Chrome",
            operating_system="Windows",
            ip_address="127.0.0.1",
            user_agent="Synthetic session test",
            last_activity_at=current,
            last_seen_at=current,
            expires_at=expires_at or current + timedelta(days=30),
            is_revoked=revoked,
            is_trusted=trusted,
        )
    )
    return record.id


async def test_list_current_rename_revoke_and_revoke_others(
    session_db: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    user_id = await _user(session_db)
    current_id = await _session(
        session_db,
        user_id,
        token_marker="a",
        display_name="Pixel 9",
        current=now,
        trusted=True,
    )
    other_id = await _session(
        session_db,
        user_id,
        token_marker="b",
        display_name="Office Laptop",
        current=now - timedelta(minutes=1),
    )
    third_id = await _session(
        session_db,
        user_id,
        token_marker="c",
        display_name="Tablet",
        current=now - timedelta(minutes=2),
    )
    events = RecordingPublisher()
    service = SessionManagementService(
        session_db,
        SqlAlchemyRefreshSessionRepository(session_db),
        events,
    )

    records = await service.list_active(user_id)
    assert [record.id for record in records] == [current_id, other_id, third_id]
    assert (await service.current(user_id, current_id)).is_trusted

    renamed = await service.rename(user_id, other_id, "My MacBook")
    assert renamed.display_name == "My MacBook"
    assert renamed.version == 2
    with pytest.raises(Exception, match="logout"):
        await service.revoke(
            user_id,
            current_id,
            current_session_id=current_id,
        )
    await service.revoke(
        user_id,
        other_id,
        current_session_id=current_id,
    )
    assert [record.id for record in await service.list_active(user_id)] == [
        current_id,
        third_id,
    ]
    assert await service.revoke_others(user_id, current_id) == 1
    assert [record.id for record in await service.list_active(user_id)] == [current_id]
    assert any(isinstance(event, SessionRenamed) for event in events.events)
    assert any(isinstance(event, SessionRevoked) for event in events.events)
    assert any(isinstance(event, OtherSessionsRevoked) for event in events.events)


async def test_revoking_an_already_revoked_session_conflicts(
    session_db: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    user_id = await _user(session_db)
    session_id = await _session(
        session_db,
        user_id,
        token_marker="d",
        display_name="Revoked",
        current=now,
        revoked=True,
    )
    service = SessionManagementService(
        session_db,
        SqlAlchemyRefreshSessionRepository(session_db),
        RecordingPublisher(),
    )
    with pytest.raises(Exception, match="already revoked"):
        await service.revoke(
            user_id,
            session_id,
            current_session_id=UUID(int=999),
        )


async def test_activity_updates_are_throttled(session_db: AsyncSession) -> None:
    now = datetime.now(UTC)
    user_id = await _user(session_db)
    session_id = await _session(
        session_db,
        user_id,
        token_marker="e",
        display_name="Activity",
        current=now - timedelta(minutes=10),
    )
    repository = SqlAlchemyRefreshSessionRepository(session_db)
    changed = await repository.touch_activity(
        session_id,
        observed_at=now,
        write_before=now - timedelta(minutes=5),
        ip_address="203.0.113.1",
        user_agent="Mozilla/5.0 Chrome/120.0 Windows NT 10.0",
        browser="Chrome",
        operating_system="Windows",
        device_type="desktop",
        platform="Windows",
    )
    throttled = await repository.touch_activity(
        session_id,
        observed_at=now + timedelta(minutes=1),
        write_before=now - timedelta(minutes=4),
        ip_address="203.0.113.2",
        user_agent="Changed",
        browser="Unknown",
        operating_system="Unknown",
        device_type="unknown",
        platform="Unknown",
    )
    record = await repository.get_by_id(session_id)
    assert changed is True
    assert throttled is False
    assert record is not None
    assert str(record.last_ip) == "203.0.113.1"
    assert record.last_browser == "Chrome"


async def test_cleanup_revokes_expired_and_deletes_after_retention(
    session_db: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    user_id = await _user(session_db)
    await _session(
        session_db,
        user_id,
        token_marker="f",
        display_name="Expired",
        current=now - timedelta(days=3),
        expires_at=now - timedelta(days=2),
    )
    deletion_id = await _session(
        session_db,
        user_id,
        token_marker="0",
        display_name="Old revoked",
        current=now - timedelta(days=45),
        expires_at=now - timedelta(days=44),
        revoked=True,
    )
    events = RecordingPublisher()
    repository = SqlAlchemyRefreshSessionRepository(session_db)
    cleanup = SessionCleanupService(
        session_db,
        repository,
        events,
        retention=timedelta(days=30),
        batch_size=100,
    )

    revoked, deleted = await cleanup.run()

    assert revoked == 1
    assert deleted == 1
    assert await repository.get_by_id(deletion_id) is None
    assert isinstance(events.events[-1], SessionCleanupCompleted)


def test_device_parser_normalizes_supported_metadata() -> None:
    phone = parse_device(
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) "
        "AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36"
    )
    assert phone.browser == "Chrome"
    assert phone.operating_system == "Android"
    assert phone.device_type == "mobile"
    assert phone.platform == "Android"


def test_session_metrics_have_no_labels() -> None:
    SESSION_REVOCATIONS.inc(0)
    SESSION_CLEANUP_EXECUTIONS.inc(0)
    metrics = generate_latest().decode()
    assert "fashion_network_identity_session_revocations_total" in metrics
    assert "fashion_network_identity_session_cleanup_executions_total" in metrics


def test_session_routes_are_fully_described_in_openapi(
    test_settings: Settings,
) -> None:
    schema = create_application(test_settings).openapi()
    paths = schema["paths"]
    assert set(paths["/api/v1/sessions"]) == {"get"}
    assert set(paths["/api/v1/sessions/current"]) == {"get"}
    assert set(paths["/api/v1/sessions/{session_id}"]) == {"patch", "delete"}
    assert set(paths["/api/v1/sessions/revoke-others"]) == {"post"}
    assert (
        paths["/api/v1/sessions/{session_id}"]["patch"]["responses"]["409"]["content"][
            "application/problem+json"
        ]["example"]["code"]
        == "conflict"
    )
    response_properties = schema["components"]["schemas"]["SessionResponse"][
        "properties"
    ]
    assert {
        "current",
        "is_trusted",
        "can_rename",
        "can_revoke",
        "session_version",
    }.issubset(response_properties)
