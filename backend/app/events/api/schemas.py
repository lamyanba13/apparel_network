from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.products.domain import OutboxStatus


class OutboxEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    event_name: str
    occurred_at: datetime
    status: OutboxStatus
    available_at: datetime
    attempts: int
    locked_at: datetime | None
    locked_by: str | None
    dispatched_at: datetime | None
    published_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class OutboxEventListResponse(BaseModel):
    items: list[OutboxEventResponse]
