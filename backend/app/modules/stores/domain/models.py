from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class StoreStatus(StrEnum):
    """Operational lifecycle for a physical participating store."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class VerificationStatus(StrEnum):
    """Administrative verification state, separate from operation."""

    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class StoreAddress:
    address: str
    city: str
    district: str
    state: str
    country: str
    postal_code: str
    latitude: Decimal | None = None
    longitude: Decimal | None = None


@dataclass(frozen=True, slots=True)
class StoreContact:
    phone: str
    email: str
    website: str | None = None


@dataclass(frozen=True, slots=True)
class Store:
    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: str | None
    contact: StoreContact
    address: StoreAddress
    logo_url: str | None
    banner_url: str | None
    status: StoreStatus
    verification_status: VerificationStatus
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    version: int
