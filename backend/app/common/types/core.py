from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import JsonValue

type Uuid = UUID
type Timestamp = datetime
type RequestIdentifier = UUID
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """Transport placeholder populated only after future authentication exists."""

    user_id: UUID
    roles: tuple[str, ...] = ()
