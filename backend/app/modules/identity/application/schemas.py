from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.modules.identity.domain import (
    is_argon2id_hash,
    is_sha256_hex_digest,
    normalize_email,
)


class PersistenceSchema(BaseModel):
    """Strict base for internal persistence DTOs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        from_attributes=True,
        str_strip_whitespace=True,
    )


def _validate_email(value: str) -> str:
    normalized = normalize_email(value)
    if (
        not normalized
        or len(normalized) > 320
        or normalized.count("@") != 1
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("email must be a valid normalized identity address")
    local_part, domain = normalized.split("@", maxsplit=1)
    if not local_part or not domain or "." not in domain:
        raise ValueError("email must include a local part and domain")
    return value.strip()


def _validate_argon2id(value: str | SecretStr) -> SecretStr:
    raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
    if not is_argon2id_hash(raw_value):
        raise ValueError("password hash must use Argon2id")
    return SecretStr(raw_value)


def _validate_token_hash(value: str | SecretStr) -> SecretStr:
    raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
    if not is_sha256_hex_digest(raw_value):
        raise ValueError("token hash must be a lowercase SHA-256 digest")
    return SecretStr(raw_value)


class UserCreate(PersistenceSchema):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    password_hash: SecretStr
    is_email_verified: bool = False
    email_verified_at: AwareDatetime | None = None
    is_active: bool = True
    is_locked: bool = False
    deleted_at: AwareDatetime | None = None
    created_by_id: UUID | None = None
    updated_by_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)

    @field_validator("password_hash", mode="before")
    @classmethod
    def validate_password_hash(cls, value: str | SecretStr) -> SecretStr:
        return _validate_argon2id(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> UserCreate:
        if self.is_email_verified != (self.email_verified_at is not None):
            raise ValueError(
                "email verification flag and timestamp must change together"
            )
        if self.deleted_at is not None and self.is_active:
            raise ValueError("a soft-deleted user cannot remain active")
        return self

    @property
    def normalized_email(self) -> str:
        return normalize_email(self.email)


class UserRecord(PersistenceSchema):
    id: UUID
    email: str
    normalized_email: str
    display_name: str
    password_hash: SecretStr
    is_email_verified: bool
    email_verified_at: AwareDatetime | None
    is_active: bool
    is_locked: bool
    deleted_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    version: int = Field(ge=1)
    created_by_id: UUID | None
    updated_by_id: UUID | None


class RoleCreate(PersistenceSchema):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_system: bool = False
    is_immutable: bool = False

    @model_validator(mode="after")
    def validate_immutable_role(self) -> RoleCreate:
        if self.is_immutable and not self.is_system:
            raise ValueError("only a system role may be immutable")
        return self


class RoleRecord(RoleCreate):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    version: int = Field(ge=1)


class PermissionCreate(PersistenceSchema):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    resource: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)


class PermissionRecord(PermissionCreate):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    version: int = Field(ge=1)


class UserRoleCreate(PersistenceSchema):
    user_id: UUID
    role_id: UUID
    assigned_by_id: UUID | None = None


class UserRoleRecord(UserRoleCreate):
    created_at: AwareDatetime


class RolePermissionCreate(PersistenceSchema):
    role_id: UUID
    permission_id: UUID
    assigned_by_id: UUID | None = None


class RolePermissionRecord(RolePermissionCreate):
    created_at: AwareDatetime


class RefreshSessionCreate(PersistenceSchema):
    user_id: UUID
    refresh_token_hash: SecretStr
    device_name: str = Field(min_length=1, max_length=120)
    browser: str | None = Field(default=None, max_length=120)
    operating_system: str | None = Field(default=None, max_length=120)
    ip_address: IPv4Address | IPv6Address
    user_agent: str = Field(min_length=1, max_length=1024)
    last_activity_at: AwareDatetime
    expires_at: AwareDatetime
    is_revoked: bool = False

    @field_validator("refresh_token_hash", mode="before")
    @classmethod
    def validate_refresh_token_hash(cls, value: str | SecretStr) -> SecretStr:
        return _validate_token_hash(value)

    @model_validator(mode="after")
    def validate_expiry(self) -> RefreshSessionCreate:
        if self.expires_at <= self.last_activity_at:
            raise ValueError("session expiry must follow its last activity")
        return self


class RefreshSessionRecord(RefreshSessionCreate):
    id: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    version: int = Field(ge=1)


class PasswordHistoryCreate(PersistenceSchema):
    user_id: UUID
    password_hash: SecretStr

    @field_validator("password_hash", mode="before")
    @classmethod
    def validate_password_hash(cls, value: str | SecretStr) -> SecretStr:
        return _validate_argon2id(value)


class PasswordHistoryRecord(PasswordHistoryCreate):
    id: UUID
    created_at: AwareDatetime


class LoginAttemptCreate(PersistenceSchema):
    occurred_at: AwareDatetime
    ip_address: IPv4Address | IPv6Address
    email: str = Field(min_length=3, max_length=320)
    success: bool
    reason: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_attempt_email(cls, value: str) -> str:
        _validate_email(value)
        return normalize_email(value)

    @model_validator(mode="after")
    def validate_reason(self) -> LoginAttemptCreate:
        if not self.success and not self.reason:
            raise ValueError("failed login attempts require a reason")
        return self


class LoginAttemptRecord(LoginAttemptCreate):
    id: UUID


class ExpiringTokenCreate(PersistenceSchema):
    user_id: UUID
    token_hash: SecretStr
    expires_at: AwareDatetime
    is_used: bool = False

    @field_validator("token_hash", mode="before")
    @classmethod
    def validate_token_hash(cls, value: str | SecretStr) -> SecretStr:
        return _validate_token_hash(value)


class EmailVerificationTokenCreate(ExpiringTokenCreate):
    pass


class PasswordResetTokenCreate(ExpiringTokenCreate):
    pass


class ExpiringTokenRecord(ExpiringTokenCreate):
    id: UUID
    created_at: AwareDatetime


class EmailVerificationTokenRecord(ExpiringTokenRecord):
    pass


class PasswordResetTokenRecord(ExpiringTokenRecord):
    pass
