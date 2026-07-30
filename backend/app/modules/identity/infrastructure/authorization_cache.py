from __future__ import annotations

import json
import logging
from time import time_ns
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.modules.identity.application.authorization import PermissionCache
from app.modules.identity.domain.authorization import AuthorizationSnapshot

logger = logging.getLogger(__name__)

_NAMESPACE = "fashion-network:identity:authorization:v1"
_GENERATION_KEY = f"{_NAMESPACE}:generation"
_PRINCIPAL_VERSION_PREFIX = f"{_NAMESPACE}:principal-version"


class RedisPermissionCache(PermissionCache):
    """Versioned, fail-open performance cache for authoritative RBAC state."""

    def __init__(self, redis_url: str, *, ttl_seconds: int) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    async def get(self, user_id: UUID) -> AuthorizationSnapshot | None:
        try:
            raw = await self._redis.get(await self._key(user_id))
            if raw is None:
                return None
            value = json.loads(raw)
            return AuthorizationSnapshot(
                roles=frozenset(value["roles"]),
                permissions=frozenset(value["permissions"]),
            )
        except (RedisError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            logger.warning("identity.permission_cache_unavailable")
            return None

    async def set(self, user_id: UUID, snapshot: AuthorizationSnapshot) -> None:
        value = json.dumps(
            {
                "roles": sorted(snapshot.roles),
                "permissions": sorted(snapshot.permissions),
            },
            separators=(",", ":"),
        )
        try:
            await self._redis.set(
                await self._key(user_id),
                value,
                ex=self._ttl_seconds,
            )
        except RedisError:
            logger.warning("identity.permission_cache_unavailable")

    async def invalidate_user(self, user_id: UUID) -> None:
        try:
            await self._redis.incr(self._principal_version_key(user_id))
        except RedisError:
            logger.warning("identity.permission_cache_invalidation_failed")

    async def invalidate_all(self) -> None:
        try:
            if not await self._redis.exists(_GENERATION_KEY):
                await self._redis.set(_GENERATION_KEY, str(time_ns()), nx=True)
            else:
                await self._redis.incr(_GENERATION_KEY)
        except RedisError:
            logger.warning("identity.permission_cache_invalidation_failed")

    async def close(self) -> None:
        await self._redis.aclose()

    async def _key(self, user_id: UUID) -> str:
        generation = await self._generation()
        principal_version = await self._principal_version(user_id)
        return (
            f"{_NAMESPACE}:generation:{generation}:principal:{user_id}:"
            f"version:{principal_version}"
        )

    async def _principal_version(self, user_id: UUID) -> str:
        return cast(
            str,
            await self._redis.get(self._principal_version_key(user_id)) or "0",
        )

    @staticmethod
    def _principal_version_key(user_id: UUID) -> str:
        return f"{_PRINCIPAL_VERSION_PREFIX}:{user_id}"

    async def _generation(self) -> str:
        current = await self._redis.get(_GENERATION_KEY)
        if current is not None:
            return cast(str, current)
        candidate = str(time_ns())
        await self._redis.set(_GENERATION_KEY, candidate, nx=True)
        return cast(
            str,
            await self._redis.get(_GENERATION_KEY) or candidate,
        )
