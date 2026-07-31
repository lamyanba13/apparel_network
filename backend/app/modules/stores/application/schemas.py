from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.stores.domain import StoreAddress, StoreContact


@dataclass(frozen=True, slots=True)
class StoreCreate:
    owner_id: UUID
    name: str
    description: str | None
    contact: StoreContact
    address: StoreAddress
    logo_url: str | None = None
    banner_url: str | None = None


@dataclass(frozen=True, slots=True)
class StoreUpdate:
    values: Mapping[str, object]
    expected_version: int
