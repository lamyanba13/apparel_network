from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.common.api import install_custom_openapi
from app.common.events import DomainEvent
from app.common.exceptions import AppError
from app.core.config import Settings, get_settings
from app.modules.identity.api.authorization import (
    authorization_service_dependency,
    require_permission,
)
from app.modules.identity.api.dependencies import current_identity_dependency
from app.modules.identity.application.authorization import (
    AuthorizationService,
    PermissionResolver,
    PermissionService,
)
from app.modules.identity.application.schemas import UserCreate
from app.modules.identity.domain.authorization import (
    AuthorizationPrincipal,
    AuthorizationSnapshot,
    PermissionName,
    PermissionRegistry,
)
from app.modules.identity.domain.authorization_events import (
    AuthorizationDenied,
    AuthorizationGranted,
    PermissionCacheHit,
    PermissionCacheMiss,
    PermissionGranted,
    PermissionRevoked,
    RoleAssigned,
    RoleRevoked,
)
from app.modules.identity.domain.policies import (
    AuthorizationContext,
    DeferredBusinessAuthorizationPolicy,
    PolicyDecision,
    PolicyDecisionReason,
    PolicyOutcome,
)
from app.modules.identity.infrastructure.authorization_cache import (
    RedisPermissionCache,
)
from app.modules.identity.infrastructure.persistence.models import (
    PermissionModel,
    RoleModel,
)
from app.modules.identity.infrastructure.persistence.repositories import (
    SqlAlchemyIdentityGrantRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyRoleRepository,
    SqlAlchemyUserRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$ZGlnaWVzdA"


class MemoryPermissionCache:
    def __init__(self) -> None:
        self.values: dict[UUID, AuthorizationSnapshot] = {}
        self.user_invalidations: list[UUID] = []
        self.global_invalidations = 0

    async def get(self, user_id: UUID) -> AuthorizationSnapshot | None:
        return self.values.get(user_id)

    async def set(self, user_id: UUID, snapshot: AuthorizationSnapshot) -> None:
        self.values[user_id] = snapshot

    async def invalidate_user(self, user_id: UUID) -> None:
        self.user_invalidations.append(user_id)
        self.values.pop(user_id, None)

    async def invalidate_all(self) -> None:
        self.global_invalidations += 1
        self.values.clear()

    async def close(self) -> None:
        return None


class CollectingPublisher:
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

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
async def authorization_session(
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
        )
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
    await engine.dispose()


async def test_default_roles_permissions_assignment_and_resolution(
    authorization_session: AsyncSession,
) -> None:
    roles = (await authorization_session.scalars(select(RoleModel))).all()
    permissions = (await authorization_session.scalars(select(PermissionModel))).all()
    assert {role.name for role in roles} >= {
        "super_admin",
        "admin",
        "store_owner",
        "store_staff",
        "customer",
        "guest",
    }
    assert {permission.name for permission in permissions} >= {
        "store:view",
        "catalog:view",
        "reservation:create",
        "admin:access",
        "system:manage",
    }

    user = await SqlAlchemyUserRepository(authorization_session).add(
        UserCreate(
            email="authorization@example.com",
            display_name="Authorization Test",
            password_hash=ARGON2_HASH,
        )
    )
    cache = MemoryPermissionCache()
    publisher = CollectingPublisher()
    service = PermissionService(
        authorization_session,
        SqlAlchemyRoleRepository(authorization_session),
        SqlAlchemyPermissionRepository(authorization_session),
        SqlAlchemyIdentityGrantRepository(authorization_session),
        cache,
        PermissionRegistry(),
        publisher,
    )
    await service.assign_role(user.id, "customer")
    snapshot = await SqlAlchemyIdentityGrantRepository(
        authorization_session
    ).resolve_authorization(user.id)

    assert snapshot.roles == {"customer"}
    assert {"catalog:view", "reservation:create"} <= snapshot.permissions
    assert cache.user_invalidations == [user.id]
    assert any(isinstance(event, RoleAssigned) for event in publisher.events)

    assert await service.revoke_role(user.id, "customer") is True
    assert (
        await SqlAlchemyIdentityGrantRepository(
            authorization_session
        ).resolve_authorization(user.id)
    ).permissions == set()
    assert any(isinstance(event, RoleRevoked) for event in publisher.events)


async def test_permission_resolution_cache_decisions_events_and_invalidation(
    authorization_session: AsyncSession,
) -> None:
    user = await SqlAlchemyUserRepository(authorization_session).add(
        UserCreate(
            email="cache@example.com",
            display_name="Cache Test",
            password_hash=ARGON2_HASH,
        )
    )
    cache = MemoryPermissionCache()
    publisher = CollectingPublisher()
    grants = SqlAlchemyIdentityGrantRepository(authorization_session)
    management = PermissionService(
        authorization_session,
        SqlAlchemyRoleRepository(authorization_session),
        SqlAlchemyPermissionRepository(authorization_session),
        grants,
        cache,
        PermissionRegistry(),
        publisher,
    )
    await management.assign_role(user.id, "admin")
    resolver = PermissionResolver(grants, cache, publisher)
    service = AuthorizationService(resolver, PermissionRegistry(), publisher)
    principal = AuthorizationPrincipal(user_id=user.id)

    assert await service.has_permission(principal, "admin:access") is True
    await service.require_any_permission(principal, {"admin:access", "system:manage"})
    with pytest.raises(AppError) as denied:
        await service.require_all_permissions(
            principal, {"admin:access", "system:manage"}
        )
    assert denied.value.status_code == 403
    await service.require_role(principal, "admin")

    assert any(isinstance(event, PermissionCacheMiss) for event in publisher.events)
    assert any(isinstance(event, PermissionCacheHit) for event in publisher.events)
    assert any(isinstance(event, AuthorizationGranted) for event in publisher.events)
    assert any(isinstance(event, AuthorizationDenied) for event in publisher.events)

    await management.assign_permission("admin", "system:manage")
    assert any(isinstance(event, PermissionGranted) for event in publisher.events)
    await management.revoke_permission("admin", "system:manage")
    assert any(isinstance(event, PermissionRevoked) for event in publisher.events)
    await management.revoke_permission("admin", "admin:access")
    assert cache.global_invalidations == 3
    assert await service.has_permission(principal, "admin:access") is False


async def test_business_policy_placeholders_deny_by_default() -> None:
    policy = DeferredBusinessAuthorizationPolicy()
    principal = AuthorizationPrincipal(user_id=UUID(int=1))
    contexts = (
        AuthorizationContext(
            principal=principal,
            resource=object(),
            action=PermissionName.STORE_UPDATE,
            metadata={"source": "test"},
        ),
        AuthorizationContext(
            principal=principal,
            resource=object(),
            action=PermissionName.CATALOG_UPDATE,
        ),
        AuthorizationContext(
            principal=principal,
            resource=object(),
            action=PermissionName.INVENTORY_UPDATE,
        ),
    )
    decisions = (
        await policy.can_update_store(contexts[0]),
        await policy.can_publish_catalog(contexts[1]),
        await policy.can_delete_inventory(contexts[2]),
    )

    assert all(decision.allowed is False for decision in decisions)
    assert all(decision.outcome is PolicyOutcome.DENIED for decision in decisions)
    assert all(
        decision.reason is PolicyDecisionReason.POLICY_NOT_IMPLEMENTED
        for decision in decisions
    )
    assert contexts[0].metadata == {"source": "test"}
    with pytest.raises(TypeError):
        contexts[0].metadata["source"] = "changed"


def test_policy_decision_can_capture_missing_permission() -> None:
    decision = PolicyDecision.deny(
        policy="store.update",
        reason=PolicyDecisionReason.MISSING_PERMISSION,
        missing_permission=PermissionName.STORE_UPDATE,
    )

    assert decision.allowed is False
    assert decision.missing_permission == "store:update"


def test_registry_rejects_noncanonical_permissions_and_roles() -> None:
    registry = PermissionRegistry()

    assert (
        registry.parse(PermissionName.CATALOG_VIEW).name == PermissionName.CATALOG_VIEW
    )
    assert set(registry.foundational()) == set(PermissionName)
    assert registry.validate_role("store_owner") == "store_owner"
    with pytest.raises(ValueError):
        registry.parse("catalog.view")
    with pytest.raises(ValueError):
        registry.parse("Catalog:view")
    with pytest.raises(ValueError):
        registry.validate_role("Store Owner")


async def test_redis_permission_cache_round_trip_and_invalidation(
    test_settings: Settings,
) -> None:
    cache = RedisPermissionCache(
        test_settings.redis_url,
        ttl_seconds=60,
    )
    user_id = uuid4()
    snapshot = AuthorizationSnapshot(
        roles=frozenset({"customer"}),
        permissions=frozenset({"catalog:view"}),
    )
    try:
        await cache.set(user_id, snapshot)
        assert await cache.get(user_id) == snapshot

        await cache.invalidate_user(user_id)
        assert await cache.get(user_id) is None

        await cache.set(user_id, snapshot)
        await cache.invalidate_all()
        assert await cache.get(user_id) is None
    finally:
        await cache.invalidate_user(user_id)
        await cache.close()


def test_authorization_dependency_documents_bearer_security_and_requirement(
    test_settings: Settings,
) -> None:
    application = FastAPI()

    @application.get(
        "/protected",
        dependencies=[require_permission("catalog:view")],
    )
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    install_custom_openapi(application, test_settings)
    operation = application.openapi()["paths"]["/protected"]["get"]

    assert operation["security"] == [{"HTTPBearer": []}]
    assert operation["x-authorization"] == [
        {"kind": "permission", "values": ["catalog:view"]}
    ]


def test_permission_dependency_invokes_authorization_service() -> None:
    application = FastAPI()
    calls: list[tuple[AuthorizationPrincipal, str]] = []

    class StubAuthorizationService:
        async def require_permission(
            self,
            identity: AuthorizationPrincipal,
            permission: str,
        ) -> None:
            calls.append((identity, permission))

    identity = SimpleNamespace(
        user=SimpleNamespace(id=UUID(int=10)),
        session=SimpleNamespace(id=UUID(int=11)),
    )
    application.dependency_overrides[current_identity_dependency] = lambda: identity
    application.dependency_overrides[authorization_service_dependency] = (
        StubAuthorizationService
    )

    @application.get(
        "/protected",
        dependencies=[require_permission("catalog:view")],
    )
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(application) as client:
        assert client.get("/protected").json() == {"ok": True}

    assert calls == [
        (
            AuthorizationPrincipal(
                user_id=identity.user.id,
                session_id=identity.session.id,
            ),
            "catalog:view",
        )
    ]


def test_authorization_metrics_are_exposed_without_labels() -> None:
    exposition = generate_latest().decode()

    for metric in (
        "fashion_network_identity_authorization_checks_total",
        "fashion_network_identity_authorization_denied_total",
        "fashion_network_identity_permission_cache_hits_total",
        "fashion_network_identity_permission_cache_misses_total",
    ):
        assert metric in exposition
        line = next(
            item for item in exposition.splitlines() if item.startswith(f"{metric} ")
        )
        assert "{" not in line
