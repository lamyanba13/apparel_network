from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.inventory.domain import (
    InventoryMovementType,
    InventoryStatus,
    StockClassification,
    TrackingPolicy,
)


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


class InventoryAdjustmentRequest(BaseModel):
    quantity_delta: int
    movement_type: InventoryMovementType
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)
    source: str = Field(default="manual", min_length=1, max_length=100)
    reference_id: UUID | None = None


class InventoryReconciliationRequest(BaseModel):
    physical_count: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    version: int = Field(ge=1)
    source: str = Field(default="physical_count", min_length=1, max_length=100)
    reference_id: UUID | None = None


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inventory_id: UUID
    store_id: UUID
    variant_id: UUID
    movement_type: InventoryMovementType
    quantity_delta: int
    previous_on_hand: int
    new_on_hand: int
    previous_available: int
    new_available: int
    reservation_quantity: int
    reason: str
    actor_id: UUID
    source: str
    reference_id: UUID | None
    created_at: datetime


class InventoryMovementListResponse(BaseModel):
    items: list[InventoryMovementResponse]
    page: PageMetadata


class InventoryStockResponse(BaseModel):
    inventory: InventoryResponse
    active_reservation_quantity: int
    effective_available: int
    classification: StockClassification


class InventoryStockListResponse(BaseModel):
    items: list[InventoryStockResponse]
    page: PageMetadata


class RetailerOrderActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    order_number: str
    status: str
    placed_at: datetime
    shipment_status: str | None


class RetailerShipmentActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    order_id: UUID
    status: str
    created_at: datetime


class RetailerOrderActivityListResponse(BaseModel):
    items: list[RetailerOrderActivityResponse]
    page: PageMetadata


class RetailerShipmentActivityListResponse(BaseModel):
    items: list[RetailerShipmentActivityResponse]
    page: PageMetadata


class RetailerOperationsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: UUID
    active_products: int
    active_variants: int
    in_stock_variants: int
    low_stock_variants: int
    out_of_stock_variants: int
    orders_awaiting_fulfillment: int
    orders_requiring_attention: int
    shipments_pending_fulfillment: int
    shipments_in_transit: int
    recent_movements: list[InventoryMovementResponse]
