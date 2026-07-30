from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class SessionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "0195f36d-9b08-7b22-ae8e-72bb3ce42439",
                    "display_name": "Office Laptop",
                    "browser": "Chrome",
                    "operating_system": "Windows",
                    "device_type": "desktop",
                    "platform": "Windows",
                    "last_ip": "203.0.113.10",
                    "last_seen_at": "2026-07-30T12:30:00Z",
                    "created_at": "2026-07-29T08:00:00Z",
                    "expires_at": "2026-08-28T08:00:00Z",
                    "country": None,
                    "city": None,
                    "is_trusted": False,
                    "risk_score": None,
                    "session_version": 3,
                    "current": True,
                    "can_rename": True,
                    "can_revoke": False,
                }
            ]
        }
    )

    id: UUID
    display_name: str
    browser: str | None
    operating_system: str | None
    device_type: str | None
    platform: str | None
    last_ip: str | None
    last_seen_at: AwareDatetime
    created_at: AwareDatetime
    expires_at: AwareDatetime
    country: str | None
    city: str | None
    is_trusted: bool
    risk_score: int | None
    session_version: int = Field(ge=1)
    current: bool
    can_rename: bool
    can_revoke: bool


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class RenameSessionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"display_name": "My MacBook"}]},
    )
    display_name: str = Field(min_length=1, max_length=120)


class RevokeOthersResponse(BaseModel):
    revoked_sessions: int = Field(ge=0)
