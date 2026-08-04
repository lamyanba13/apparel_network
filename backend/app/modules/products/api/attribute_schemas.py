from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.products.domain import AttributeStatus, AttributeType


class AttributeCreateRequest(BaseModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(min_length=1, max_length=180)
    attribute_type: AttributeType = Field(alias="type")
    description: str | None = Field(default=None, max_length=2000)
    required: bool = False
    filterable: bool = False
    searchable: bool = False
    sort_order: int = Field(default=0, ge=0)
    status: AttributeStatus = AttributeStatus.ACTIVE


class AttributeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    slug: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    required: bool | None = None
    filterable: bool | None = None
    searchable: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    status: AttributeStatus | None = None
    version: int = Field(ge=1)


class AttributeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    store_id: UUID
    name: str
    slug: str
    attribute_type: AttributeType
    description: str | None
    required: bool
    filterable: bool
    searchable: bool
    sort_order: int
    status: AttributeStatus
    version: int
    created_at: datetime
    updated_at: datetime


class AttributeValueCreateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200)
    sort_order: int = Field(default=0, ge=0)


class AttributeValueUpdateRequest(BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = Field(default=None, ge=0)
    version: int = Field(ge=1)


class AttributeValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attribute_id: UUID
    value: str
    slug: str
    sort_order: int
    version: int
    created_at: datetime
    updated_at: datetime


class VariantAttributeAssignmentRequest(BaseModel):
    attribute_value_id: UUID
    version: int = Field(ge=1)


class VariantAttributeAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    variant_id: UUID
    attribute_value_id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class VariantAttributeValueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    assignment_id: UUID
    attribute_id: UUID
    attribute_name: str
    attribute_slug: str
    attribute_type: AttributeType
    attribute_sort_order: int
    value_id: UUID
    value: str
    value_slug: str
    value_sort_order: int
