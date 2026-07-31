from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PageMetadata
from app.modules.stores.domain import StoreMembershipRole, StoreMembershipStatus


class StoreMembershipInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: StoreMembershipRole = StoreMembershipRole.STAFF


class StoreMembershipUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    role: StoreMembershipRole | None = None
    status: StoreMembershipStatus | None = None


class StoreMembershipVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)


class StoreMembershipResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    store_id: UUID
    user_id: UUID
    role: StoreMembershipRole
    status: StoreMembershipStatus
    invited_by_id: UUID
    invitation_expires_at: datetime | None
    accepted_at: datetime | None
    removed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class StoreMembershipListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StoreMembershipResponse]
    page: PageMetadata
