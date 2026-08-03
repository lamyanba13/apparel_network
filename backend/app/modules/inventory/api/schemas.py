from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.inventory.domain import InventoryStatus, TrackingPolicy


class InventoryCreateRequest(BaseModel):
    variant_id: UUID
    quantity_on_hand: int = Field(ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    status: InventoryStatus = InventoryStatus.ACTIVE
    tracking_policy: TrackingPolicy = TrackingPolicy.TRACK
    low_stock_threshold: int = Field(default=0, ge=0)


class InventoryUpdateRequest(BaseModel):
    quantity_on_hand: int | None = Field(default=None, ge=0)
    quantity_reserved: int | None = Field(default=None, ge=0)
    status: InventoryStatus | None = None
    tracking_policy: TrackingPolicy | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0)
    version: int = Field(ge=1)


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    variant_id: UUID
    product_id: UUID
    catalog_id: UUID
    store_id: UUID
    sku_snapshot: str
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    status: InventoryStatus
    tracking_policy: TrackingPolicy
    low_stock_threshold: int
    created_at: datetime
    updated_at: datetime
    version: int


class InventoryListResponse(BaseModel):
    items: list[InventoryResponse]
    page: PageMetadata
