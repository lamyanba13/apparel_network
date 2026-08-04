from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.shipments.domain import ShipmentStatus


class ShipmentCreateRequest(BaseModel):
    order_id: UUID
    reservation_id: UUID
    payment_id: UUID
    shipping_method: str = Field(min_length=1, max_length=100)


class PackageCreateRequest(BaseModel):
    package_number: str = Field(min_length=1, max_length=100)
    weight: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    length: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    width: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    height: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class ShipmentPackRequest(BaseModel):
    version: int = Field(ge=1)
    packages: list[PackageCreateRequest] = Field(min_length=1, max_length=100)


class ShipmentTransitionRequest(BaseModel):
    version: int = Field(ge=1)


class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    reservation_id: UUID
    payment_id: UUID
    customer_id: UUID
    store_id: UUID
    status: ShipmentStatus
    carrier: str | None
    tracking_number: str | None
    tracking_url: str | None
    shipping_method: str
    estimated_delivery_at: datetime | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID | None
    updated_by_id: UUID | None


class ShipmentPackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shipment_id: UUID
    package_number: str
    weight: Decimal
    length: Decimal
    width: Decimal
    height: Decimal
    label_url: str | None
    created_at: datetime


class ShipmentTrackingEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shipment_id: UUID
    status: ShipmentStatus
    location: str | None
    description: str
    occurred_at: datetime


class ShipmentDetailResponse(ShipmentResponse):
    packages: list[ShipmentPackageResponse]
    tracking: list[ShipmentTrackingEventResponse]


class ShipmentListResponse(BaseModel):
    items: list[ShipmentResponse]
    page: PageMetadata


class ShipmentTrackingResponse(BaseModel):
    items: list[ShipmentTrackingEventResponse]
