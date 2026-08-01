from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.domain import StoreStatus, VerificationStatus
from app.modules.stores.domain.media import StoreMediaStatus
from app.modules.stores.domain.search import StoreSearchDocument
from app.modules.stores.infrastructure.persistence.media_models import StoreMediaModel
from app.modules.stores.infrastructure.persistence.models import StoreModel
from app.modules.stores.infrastructure.persistence.operating_hours_models import (
    StoreOperatingHoursModel,
)


async def build_store_document(
    session: AsyncSession,
    store_id: UUID,
) -> StoreSearchDocument | None:
    store = await session.scalar(select(StoreModel).where(StoreModel.id == store_id))
    if store is None:
        return None
    media_counts = await session.execute(
        select(StoreMediaModel.media_type, func.count(StoreMediaModel.id))
        .where(
            StoreMediaModel.store_id == store_id,
            StoreMediaModel.status == StoreMediaStatus.ACTIVE,
            StoreMediaModel.deleted_at.is_(None),
        )
        .group_by(StoreMediaModel.media_type)
    )
    counts = {
        getattr(media_type, "value", str(media_type)): int(count)
        for media_type, count in media_counts
    }
    eligible = (
        store.deleted_at is None
        and store.status is StoreStatus.ACTIVE
        and store.verification_status is VerificationStatus.VERIFIED
    )
    if not eligible:
        return None
    return StoreSearchDocument(
        store_id=store.id,
        name=store.name,
        slug=store.slug,
        description=store.description,
        category=None,
        city=store.city,
        state=store.state,
        country=store.country,
        postal_code=store.postal_code,
        latitude=store.latitude,
        longitude=store.longitude,
        verified=True,
        active=True,
        currently_open=await _currently_open(session, store_id),
        logo_exists=counts.get("logo", 0) > 0,
        banner_exists=counts.get("banner", 0) > 0,
        media_count=sum(counts.values()),
        created_at=store.created_at or datetime.now(UTC),
        updated_at=store.updated_at or datetime.now(UTC),
    )


async def _currently_open(session: AsyncSession, store_id: UUID) -> bool:
    now = datetime.now(UTC)
    rules = list(
        await session.scalars(
            select(StoreOperatingHoursModel).where(
                StoreOperatingHoursModel.store_id == store_id,
                StoreOperatingHoursModel.deleted_at.is_(None),
                (
                    StoreOperatingHoursModel.effective_from.is_(None)
                    | (StoreOperatingHoursModel.effective_from <= now)
                ),
                (
                    StoreOperatingHoursModel.effective_until.is_(None)
                    | (StoreOperatingHoursModel.effective_until > now)
                ),
            )
        )
    )
    if not rules:
        return False
    timezone = ZoneInfo(rules[0].timezone)
    local = now.astimezone(timezone)
    eligible = [rule for rule in rules if rule.day_of_week == local.weekday()]
    temporary = [rule for rule in eligible if rule.effective_from is not None]
    selected = temporary or [rule for rule in eligible if rule.effective_from is None]
    if not selected:
        return False
    priority = max(rule.priority for rule in selected)
    selected = [rule for rule in selected if rule.priority == priority]
    local_time = local.timetz().replace(tzinfo=None)
    for rule in selected:
        if rule.is_24_hours:
            return True
        if (
            not rule.is_closed
            and rule.opening_time is not None
            and rule.closing_time is not None
            and rule.opening_time <= local_time < rule.closing_time
        ):
            return True
    return False
