from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StoreSearchDocument:
    store_id: UUID
    name: str
    slug: str
    description: str | None
    category: str | None
    city: str
    state: str
    country: str
    postal_code: str
    latitude: Decimal | None
    longitude: Decimal | None
    verified: bool
    active: bool
    currently_open: bool
    logo_exists: bool
    banner_exists: bool
    media_count: int
    created_at: datetime
    updated_at: datetime

    def public_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "store_id": str(self.store_id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "category": self.category,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "postal_code": self.postal_code,
            "latitude": float(self.latitude) if self.latitude is not None else None,
            "longitude": float(self.longitude) if self.longitude is not None else None,
            "verified": self.verified,
            "active": self.active,
            "currently_open": self.currently_open,
            "logo_exists": self.logo_exists,
            "banner_exists": self.banner_exists,
            "media_count": self.media_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if self.latitude is not None and self.longitude is not None:
            document["_geo"] = {
                "lat": float(self.latitude),
                "lng": float(self.longitude),
            }
        return document


@dataclass(frozen=True, slots=True)
class StoreSearchResult:
    document: StoreSearchDocument
    score: float | None = None


@dataclass(frozen=True, slots=True)
class StoreSearchPage:
    items: tuple[StoreSearchResult, ...]
    total: int
    limit: int
    offset: int
    processing_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class StoreAutocompleteItem:
    store_id: UUID
    name: str
    slug: str
