from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.reservations.domain import ReservationStatus


class ReservationCreateRequest(BaseModel):
    order_id: UUID
    payment_id: UUID
    expires_at: datetime | None = None


class ReservationTransitionRequest(BaseModel):
    version: int = Field(ge=1, description="Current Reservation version")


class ReservationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reservation_id: UUID
    inventory_item_id: UUID
    variant_id: UUID
    quantity: int
    inventory_version: int
    created_at: datetime


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: ReservationStatus
    expires_at: datetime
    released_at: datetime | None
    consumed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ReservationDetailResponse(ReservationResponse):
    items: list[ReservationItemResponse]


class ReservationListResponse(BaseModel):
    items: list[ReservationResponse]
    page: PageMetadata


class ReservationStatusResponse(BaseModel):
    reservation_id: UUID
    status: ReservationStatus
    expires_at: datetime
    checked_at: datetime
