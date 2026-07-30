from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, TypeVar
from uuid import UUID

from pydantic import JsonValue


class DomainEvent(Protocol):
    """Minimal contract implemented by future module-owned domain events."""

    @property
    def event_id(self) -> UUID: ...

    @property
    def event_name(self) -> str: ...

    @property
    def schema_version(self) -> int: ...

    @property
    def occurred_at(self) -> datetime: ...

    @property
    def correlation_id(self) -> UUID | None: ...

    @property
    def payload(self) -> Mapping[str, JsonValue]: ...


class EventPublisher(Protocol):
    """Port for future outbox-backed RabbitMQ publication."""

    async def publish(self, event: DomainEvent) -> None: ...


EventT = TypeVar("EventT", bound=DomainEvent, contravariant=True)


class EventHandler(Protocol[EventT]):
    """Consumer contract implemented by future module application handlers."""

    async def handle(self, event: EventT) -> None: ...
