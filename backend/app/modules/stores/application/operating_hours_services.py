from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.common.context import maybe_get_request_context
from app.common.errors import ErrorCode, FieldError
from app.common.events import EventPublisher
from app.common.exceptions import AppError
from app.modules.stores.application.operating_hours_repositories import (
    StoreOperatingHoursRepository,
)
from app.modules.stores.application.operating_hours_schemas import (
    StoreHoursCreate,
    StoreHoursUpdate,
)
from app.modules.stores.application.repositories import StoreRepository
from app.modules.stores.domain.operating_hours import (
    BusinessStatus,
    OpenState,
    OperatingInterval,
    StoreOperatingHours,
    StoreSchedule,
)
from app.modules.stores.domain.operating_hours_events import (
    StoreClosed as StoreHoursClosed,
)
from app.modules.stores.domain.operating_hours_events import (
    StoreHoursCreated,
    StoreHoursDeleted,
    StoreHoursEvent,
    StoreHoursUpdated,
    StoreOpened,
    StoreScheduleActivated,
    StoreScheduleExpired,
)
from app.observability.metrics import (
    STORE_CLOSED,
    STORE_HOURS_QUERIES,
    STORE_HOURS_UPDATES,
    STORE_OPEN,
)

DEFAULT_STORE_TIMEZONE = "Asia/Kolkata"


class StoreOperatingHoursValidationService:
    def validate_create(self, values: StoreHoursCreate) -> StoreHoursCreate:
        if not 0 <= values.day_of_week <= 6:
            raise _validation("day_of_week", "Day must be between 0 and 6.")
        if values.priority < 0:
            raise _validation("priority", "Priority cannot be negative.")
        timezone = self.timezone(values.timezone)
        notes = self.notes(values.notes)
        self._validate_mode(
            values.opening_time,
            values.closing_time,
            values.is_closed,
            values.is_24_hours,
        )
        effective_from, effective_until = self._effective_period(
            values.effective_from,
            values.effective_until,
        )
        return StoreHoursCreate(
            day_of_week=values.day_of_week,
            timezone=timezone,
            opening_time=values.opening_time,
            closing_time=values.closing_time,
            is_closed=values.is_closed,
            is_24_hours=values.is_24_hours,
            effective_from=effective_from,
            effective_until=effective_until,
            priority=values.priority,
            notes=notes,
        )

    def merge(
        self,
        current: StoreOperatingHours,
        update: StoreHoursUpdate,
    ) -> StoreHoursCreate:
        allowed = {
            "day_of_week",
            "timezone",
            "opening_time",
            "closing_time",
            "is_closed",
            "is_24_hours",
            "effective_from",
            "effective_until",
            "priority",
            "notes",
        }
        if not update.values or not set(update.values) <= allowed:
            raise _validation("body", "At least one supported field is required.")
        values: dict[str, object] = {
            "day_of_week": current.day_of_week,
            "timezone": current.timezone,
            "opening_time": current.opening_time,
            "closing_time": current.closing_time,
            "is_closed": current.is_closed,
            "is_24_hours": current.is_24_hours,
            "effective_from": current.effective_from,
            "effective_until": current.effective_until,
            "priority": current.priority,
            "notes": current.notes,
            **update.values,
        }
        return self.validate_create(
            StoreHoursCreate(
                day_of_week=_integer(values["day_of_week"], "day_of_week"),
                timezone=_string(values["timezone"], "timezone"),
                opening_time=_optional_time(values["opening_time"], "opening_time"),
                closing_time=_optional_time(values["closing_time"], "closing_time"),
                is_closed=_boolean(values["is_closed"], "is_closed"),
                is_24_hours=_boolean(values["is_24_hours"], "is_24_hours"),
                effective_from=_optional_datetime(
                    values["effective_from"], "effective_from"
                ),
                effective_until=_optional_datetime(
                    values["effective_until"], "effective_until"
                ),
                priority=_integer(values["priority"], "priority"),
                notes=_optional_string(values["notes"], "notes"),
            )
        )

    def timezone(self, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 64:
            raise _validation("timezone", "Timezone must be a valid IANA name.")
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as error:
            raise _validation(
                "timezone", "Timezone must be a valid IANA name."
            ) from error
        return normalized

    def notes(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            return None
        if len(normalized) > 500:
            raise _validation("notes", "Notes cannot exceed 500 characters.")
        return normalized

    def _validate_mode(
        self,
        opening: time | None,
        closing: time | None,
        is_closed: bool,
        is_24_hours: bool,
    ) -> None:
        if is_closed and is_24_hours:
            raise _validation(
                "is_closed",
                "A schedule cannot be both closed and open 24 hours.",
            )
        if is_closed or is_24_hours:
            if opening is not None or closing is not None:
                raise _validation(
                    "opening_time",
                    "Closed and 24-hour schedules cannot define opening times.",
                )
            return
        if opening is None or closing is None:
            raise _validation(
                "opening_time",
                "Opening and closing times are required for an interval.",
            )
        if opening.tzinfo is not None or closing.tzinfo is not None:
            raise _validation(
                "opening_time",
                "Wall-clock times must not include a timezone offset.",
            )
        if opening >= closing:
            raise _validation(
                "closing_time",
                "Closing time must be later than opening time.",
            )

    def _effective_period(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[datetime | None, datetime | None]:
        if (start is None) != (end is None):
            raise _validation(
                "effective_from",
                "Temporary schedules require both effective timestamps.",
            )
        if start is None or end is None:
            return None, None
        if start.tzinfo is None or end.tzinfo is None:
            raise _validation(
                "effective_from",
                "Effective timestamps must be timezone-aware.",
            )
        normalized_start = start.astimezone(UTC)
        normalized_end = end.astimezone(UTC)
        if normalized_start >= normalized_end:
            raise _validation(
                "effective_until",
                "Effective end must be later than effective start.",
            )
        return normalized_start, normalized_end


class StoreOperatingHoursAuditService:
    def __init__(self, events: EventPublisher) -> None:
        self._events = events

    async def publish(
        self,
        event_type: type[StoreHoursEvent],
        schedule: StoreOperatingHours,
        status: OpenState,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        await self._events.publish(
            event_type(
                store_id=schedule.store_id,
                schedule_id=schedule.id,
                status=status,
                occurred_at=occurred_at or datetime.now(UTC),
                correlation_id=_correlation_id(),
            )
        )


class StoreOperatingHoursService:
    def __init__(
        self,
        stores: StoreRepository,
        hours: StoreOperatingHoursRepository,
        validation: StoreOperatingHoursValidationService,
        audit: StoreOperatingHoursAuditService,
    ) -> None:
        self._stores = stores
        self._hours = hours
        self._validation = validation
        self._audit = audit

    async def create(
        self,
        store_id: UUID,
        owner_id: UUID,
        values: StoreHoursCreate,
    ) -> StoreOperatingHours:
        await self._owned_store(store_id, owner_id)
        validated = self._validation.validate_create(values)
        await self._hours.lock_scope(
            store_id,
            validated.day_of_week,
            validated.priority,
        )
        await self._validate_against_store(store_id, validated)
        schedule = await self._hours.add(store_id, validated)
        state = self._state_for_rule(schedule, datetime.now(UTC))
        await self._audit.publish(StoreHoursCreated, schedule, state)
        if self._effective(schedule, datetime.now(UTC)):
            await self._audit.publish(StoreScheduleActivated, schedule, state)
        STORE_HOURS_UPDATES.inc()
        return schedule

    async def list(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Sequence[StoreOperatingHours]:
        await self._owned_store(store_id, owner_id)
        STORE_HOURS_QUERIES.inc()
        return await self._hours.list_for_store(store_id)

    async def today(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        now: datetime | None = None,
    ) -> StoreSchedule | None:
        await self._owned_store(store_id, owner_id)
        instant = _aware_now(now)
        rules = await self._hours.list_for_store(
            store_id,
            include_expired=False,
        )
        STORE_HOURS_QUERIES.inc()
        return self._resolve(rules, instant)

    async def update(
        self,
        store_id: UUID,
        schedule_id: UUID,
        owner_id: UUID,
        update: StoreHoursUpdate,
    ) -> StoreOperatingHours:
        await self._owned_store(store_id, owner_id)
        current = await self._required_schedule(store_id, schedule_id)
        candidate = self._validation.merge(current, update)
        await self._hours.lock_scope(
            store_id,
            candidate.day_of_week,
            candidate.priority,
        )
        await self._validate_against_store(
            store_id,
            candidate,
            exclude_id=schedule_id,
        )
        changed = await self._hours.update(
            store_id,
            schedule_id,
            values={
                "day_of_week": candidate.day_of_week,
                "timezone": candidate.timezone,
                "opening_time": candidate.opening_time,
                "closing_time": candidate.closing_time,
                "is_closed": candidate.is_closed,
                "is_24_hours": candidate.is_24_hours,
                "effective_from": candidate.effective_from,
                "effective_until": candidate.effective_until,
                "priority": candidate.priority,
                "notes": candidate.notes,
            },
            expected_version=update.expected_version,
        )
        if changed is None:
            raise _conflict("The schedule was modified by another request.")
        instant = datetime.now(UTC)
        state = self._state_for_rule(changed, instant)
        await self._audit.publish(StoreHoursUpdated, changed, state)
        if self._effective(changed, instant):
            await self._audit.publish(StoreScheduleActivated, changed, state)
        elif changed.effective_until is not None and changed.effective_until <= instant:
            await self._audit.publish(StoreScheduleExpired, changed, state)
        STORE_HOURS_UPDATES.inc()
        return changed

    async def delete(
        self,
        store_id: UUID,
        schedule_id: UUID,
        owner_id: UUID,
    ) -> None:
        await self._owned_store(store_id, owner_id)
        current = await self._required_schedule(store_id, schedule_id)
        deleted = await self._hours.soft_delete(
            store_id,
            schedule_id,
            deleted_at=datetime.now(UTC),
            expected_version=current.version,
        )
        if deleted is None:
            raise _conflict("The schedule was modified during deletion.")
        await self._audit.publish(
            StoreHoursDeleted,
            deleted,
            self._state_for_rule(deleted, datetime.now(UTC)),
        )
        STORE_HOURS_UPDATES.inc()

    async def status(
        self,
        store_id: UUID,
        owner_id: UUID,
        *,
        now: datetime | None = None,
    ) -> BusinessStatus:
        await self._owned_store(store_id, owner_id)
        instant = _aware_now(now)
        rules = await self._hours.list_for_store(
            store_id,
            include_expired=False,
        )
        schedule = self._resolve(rules, instant)
        timezone = schedule.timezone if schedule else self._timezone(rules)
        open_now, interval, is_24_hours = self._open_details(schedule, instant)
        next_opening, next_closing = self._next_transitions(
            rules,
            instant,
            timezone,
        )
        state = OpenState.OPEN if open_now else OpenState.CLOSED
        if schedule is not None and schedule.intervals:
            event_type = StoreOpened if open_now else StoreHoursClosed
            await self._audit.publish(
                event_type,
                schedule.intervals[0],
                state,
                occurred_at=instant,
            )
        STORE_HOURS_QUERIES.inc()
        (STORE_OPEN if open_now else STORE_CLOSED).inc()
        return BusinessStatus(
            store_id=store_id,
            timezone=timezone,
            current_status=state,
            open_now=open_now,
            is_24_hours=is_24_hours,
            current_interval=interval,
            today_schedule=schedule,
            next_opening=next_opening,
            next_closing=next_closing,
            temporary_override=(
                schedule.is_temporary_override if schedule is not None else False
            ),
        )

    async def _owned_store(self, store_id: UUID, owner_id: UUID) -> None:
        if await self._stores.get_for_owner(store_id, owner_id) is None:
            raise _store_not_found()

    async def _required_schedule(
        self,
        store_id: UUID,
        schedule_id: UUID,
    ) -> StoreOperatingHours:
        schedule = await self._hours.get(store_id, schedule_id)
        if schedule is None:
            raise _schedule_not_found()
        return schedule

    async def _validate_against_store(
        self,
        store_id: UUID,
        candidate: StoreHoursCreate,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        all_rules = await self._hours.list_for_store(
            store_id,
            include_expired=False,
        )
        if any(
            rule.id != exclude_id and rule.timezone != candidate.timezone
            for rule in all_rules
        ):
            raise _validation(
                "timezone",
                "All active schedules for a Store must use one timezone.",
            )
        conflicts = await self._hours.find_conflicts(
            store_id,
            candidate,
            exclude_id=exclude_id,
        )
        if any(_rules_overlap(rule, candidate) for rule in conflicts):
            raise _conflict(
                "The schedule overlaps another interval at the same priority."
            )

    def _resolve(
        self,
        rules: Sequence[StoreOperatingHours],
        instant: datetime,
    ) -> StoreSchedule | None:
        timezone = self._timezone(rules)
        local = instant.astimezone(ZoneInfo(timezone))
        eligible = [
            rule
            for rule in rules
            if rule.day_of_week == local.weekday() and self._effective(rule, instant)
        ]
        temporary = [rule for rule in eligible if rule.is_temporary]
        selected_pool = temporary or [
            rule for rule in eligible if not rule.is_temporary
        ]
        if not selected_pool:
            return None
        priority = max(rule.priority for rule in selected_pool)
        selected = tuple(
            sorted(
                (rule for rule in selected_pool if rule.priority == priority),
                key=lambda rule: (
                    rule.opening_time or time.min,
                    str(rule.id),
                ),
            )
        )
        return StoreSchedule(
            store_id=selected[0].store_id,
            day_of_week=local.weekday(),
            timezone=timezone,
            priority=priority,
            intervals=selected,
            is_temporary_override=bool(temporary),
        )

    def _open_details(
        self,
        schedule: StoreSchedule | None,
        instant: datetime,
    ) -> tuple[bool, OperatingInterval | None, bool]:
        if schedule is None:
            return False, None, False
        local_time = (
            instant.astimezone(ZoneInfo(schedule.timezone))
            .timetz()
            .replace(tzinfo=None)
        )
        for rule in schedule.intervals:
            if rule.is_closed:
                return False, None, False
            if rule.is_24_hours:
                return True, None, True
            interval = rule.interval
            if (
                interval is not None
                and interval.opening_time <= local_time < interval.closing_time
            ):
                return True, interval, False
        return False, None, False

    def _next_transitions(
        self,
        rules: Sequence[StoreOperatingHours],
        instant: datetime,
        timezone: str,
    ) -> tuple[datetime | None, datetime | None]:
        zone = ZoneInfo(timezone)
        local_now = instant.astimezone(zone)
        candidates: set[datetime] = set()
        for day_offset in range(0, 15):
            local_date = local_now.date() + timedelta(days=day_offset)
            for rule in rules:
                if rule.day_of_week != local_date.weekday():
                    continue
                if rule.opening_time is not None:
                    candidates.add(_local_boundary(local_date, rule.opening_time, zone))
                if rule.closing_time is not None:
                    candidates.add(_local_boundary(local_date, rule.closing_time, zone))
        for rule in rules:
            if rule.effective_from is not None:
                candidates.add(rule.effective_from.astimezone(UTC))
            if rule.effective_until is not None:
                candidates.add(rule.effective_until.astimezone(UTC))

        next_opening: datetime | None = None
        next_closing: datetime | None = None
        for candidate in sorted(value for value in candidates if value > instant):
            before_schedule = self._resolve(
                rules, candidate - timedelta(microseconds=1)
            )
            after_schedule = self._resolve(rules, candidate + timedelta(microseconds=1))
            before = self._open_details(
                before_schedule,
                candidate - timedelta(microseconds=1),
            )[0]
            after = self._open_details(
                after_schedule,
                candidate + timedelta(microseconds=1),
            )[0]
            if not before and after and next_opening is None:
                next_opening = candidate.astimezone(UTC)
            if before and not after and next_closing is None:
                next_closing = candidate.astimezone(UTC)
            if next_opening is not None and next_closing is not None:
                break
        return next_opening, next_closing

    @staticmethod
    def _effective(rule: StoreOperatingHours, instant: datetime) -> bool:
        if rule.effective_from is None:
            return True
        return (
            rule.effective_from <= instant
            and rule.effective_until is not None
            and instant < rule.effective_until
        )

    @staticmethod
    def _timezone(rules: Sequence[StoreOperatingHours]) -> str:
        return rules[0].timezone if rules else DEFAULT_STORE_TIMEZONE

    @staticmethod
    def _state_for_rule(
        rule: StoreOperatingHours,
        instant: datetime,
    ) -> OpenState:
        if rule.is_closed:
            return OpenState.CLOSED
        if rule.is_24_hours:
            return OpenState.OPEN
        local_time = (
            instant.astimezone(ZoneInfo(rule.timezone)).timetz().replace(tzinfo=None)
        )
        if (
            rule.opening_time is not None
            and rule.closing_time is not None
            and rule.opening_time <= local_time < rule.closing_time
        ):
            return OpenState.OPEN
        return OpenState.CLOSED


def _rules_overlap(
    existing: StoreOperatingHours,
    candidate: StoreHoursCreate,
) -> bool:
    if not _periods_overlap(
        existing.effective_from,
        existing.effective_until,
        candidate.effective_from,
        candidate.effective_until,
    ):
        return False
    if (
        existing.is_closed
        or existing.is_24_hours
        or candidate.is_closed
        or candidate.is_24_hours
    ):
        return True
    return bool(
        existing.opening_time is not None
        and existing.closing_time is not None
        and candidate.opening_time is not None
        and candidate.closing_time is not None
        and existing.opening_time < candidate.closing_time
        and candidate.opening_time < existing.closing_time
    )


def _periods_overlap(
    left_start: datetime | None,
    left_end: datetime | None,
    right_start: datetime | None,
    right_end: datetime | None,
) -> bool:
    if left_start is None or right_start is None:
        return True
    if left_end is None or right_end is None:
        return True
    return bool(left_start < right_end and right_start < left_end)


def _local_boundary(local_date: date, wall_time: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(local_date, wall_time, tzinfo=zone).astimezone(UTC)


def _aware_now(value: datetime | None) -> datetime:
    instant = value or datetime.now(UTC)
    if instant.tzinfo is None:
        raise _validation("now", "Current time must be timezone-aware.")
    return instant.astimezone(UTC)


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _validation(field, f"{field} must be an integer.")
    return value


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise _validation(field, f"{field} must be a boolean.")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _validation(field, f"{field} must be a string.")
    return value


def _optional_string(value: object, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise _validation(field, f"{field} must be a string or null.")
    return value


def _optional_time(value: object, field: str) -> time | None:
    if value is not None and not isinstance(value, time):
        raise _validation(field, f"{field} must be a local time or null.")
    return value


def _optional_datetime(value: object, field: str) -> datetime | None:
    if value is not None and not isinstance(value, datetime):
        raise _validation(field, f"{field} must be a timestamp or null.")
    return value


def _store_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store not found",
        detail="The requested Store was not found.",
        status_code=404,
    )


def _schedule_not_found() -> AppError:
    return AppError(
        code=ErrorCode.NOT_FOUND,
        title="Store schedule not found",
        detail="The requested Store schedule was not found.",
        status_code=404,
    )


def _conflict(detail: str) -> AppError:
    return AppError(
        code=ErrorCode.CONFLICT,
        title="Store schedule conflict",
        detail=detail,
        status_code=409,
    )


def _validation(field: str, message: str) -> AppError:
    return AppError(
        code=ErrorCode.VALIDATION_ERROR,
        title="Store schedule validation failed",
        detail="One or more Store schedule fields are invalid.",
        status_code=422,
        errors=[
            FieldError(
                field=field,
                code="invalid_store_schedule",
                message=message,
            )
        ],
    )


def _correlation_id() -> UUID | None:
    context = maybe_get_request_context()
    return context.correlation_id if context is not None else None
