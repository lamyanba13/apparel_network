from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    event,
    false,
    func,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.mixins import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.identity.domain import normalize_email

_USER_FOREIGN_KEY = "identity_users.id"
_ROLE_FOREIGN_KEY = "identity_roles.id"
_PERMISSION_FOREIGN_KEY = "identity_permissions.id"
_ARGON2ID_HASH_CHECK = "password_hash LIKE '$argon2id$%'"
_SHA256_HASH_CHECK = "token_hash ~ '^[0-9a-f]{64}$'"


class UserModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    """Identity profile and credential persistence record."""

    __tablename__ = "identity_users"
    __table_args__ = (
        CheckConstraint(
            "email = btrim(email) AND length(email) BETWEEN 3 AND 320",
            name="email_length",
        ),
        CheckConstraint(
            "normalized_email = lower(btrim(email))",
            name="normalized_email_matches_email",
        ),
        CheckConstraint(
            "length(btrim(display_name)) BETWEEN 1 AND 120",
            name="display_name_length",
        ),
        CheckConstraint(_ARGON2ID_HASH_CHECK, name="password_hash_argon2id"),
        CheckConstraint(
            "(is_email_verified AND email_verified_at IS NOT NULL) OR "
            "(NOT is_email_verified AND email_verified_at IS NULL)",
            name="email_verification_consistent",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR NOT is_active",
            name="deleted_user_inactive",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_identity_users_normalized_email",
            "normalized_email",
            unique=True,
        ),
        Index("ix_identity_users_created_by_id", "created_by_id"),
        Index("ix_identity_users_updated_by_id", "updated_by_id"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    is_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=True,
    )

    user_roles: Mapped[list[UserRoleModel]] = relationship(
        back_populates="user",
        foreign_keys="UserRoleModel.user_id",
        lazy="selectin",
    )
    refresh_sessions: Mapped[list[RefreshSessionModel]] = relationship(
        back_populates="user",
        lazy="selectin",
    )
    password_history: Mapped[list[PasswordHistoryModel]] = relationship(
        back_populates="user",
        lazy="selectin",
    )
    email_verification_tokens: Mapped[list[EmailVerificationTokenModel]] = relationship(
        back_populates="user", lazy="selectin"
    )
    password_reset_tokens: Mapped[list[PasswordResetTokenModel]] = relationship(
        back_populates="user",
        lazy="selectin",
    )


@event.listens_for(UserModel, "before_insert")
@event.listens_for(UserModel, "before_update")
def _normalize_user_email(
    _mapper: object,
    _connection: object,
    target: UserModel,
) -> None:
    target.email = target.email.strip()
    target.normalized_email = normalize_email(target.email)


class RoleModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "identity_roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_identity_roles_name"),
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 100",
            name="name_length",
        ),
        CheckConstraint(
            "description IS NULL OR length(description) <= 500",
            name="description_length",
        ),
        CheckConstraint(
            "NOT is_immutable OR is_system",
            name="immutable_role_is_system",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    is_immutable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    user_roles: Mapped[list[UserRoleModel]] = relationship(
        back_populates="role",
        lazy="selectin",
    )
    role_permissions: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="role",
        lazy="selectin",
    )


class PermissionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "identity_permissions"
    __table_args__ = (
        UniqueConstraint("name", name="uq_identity_permissions_name"),
        UniqueConstraint(
            "resource",
            "action",
            name="uq_identity_permissions_resource_action",
        ),
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 150",
            name="name_length",
        ),
        CheckConstraint(
            "description IS NULL OR length(description) <= 500",
            name="description_length",
        ),
        CheckConstraint(
            "length(btrim(resource)) BETWEEN 1 AND 100",
            name="resource_length",
        ),
        CheckConstraint(
            "length(btrim(action)) BETWEEN 1 AND 100",
            name="action_length",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    role_permissions: Mapped[list[RolePermissionModel]] = relationship(
        back_populates="permission",
        lazy="selectin",
    )


class UserRoleModel(Base):
    __tablename__ = "identity_user_roles"
    __table_args__ = (
        Index("ix_identity_user_roles_role_id", "role_id"),
        Index("ix_identity_user_roles_assigned_by_id", "assigned_by_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        primary_key=True,
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey(_ROLE_FOREIGN_KEY, ondelete="RESTRICT"),
        primary_key=True,
    )
    assigned_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(
        back_populates="user_roles",
        foreign_keys=[user_id],
    )
    role: Mapped[RoleModel] = relationship(back_populates="user_roles")


class RolePermissionModel(Base):
    __tablename__ = "identity_role_permissions"
    __table_args__ = (
        Index(
            "ix_identity_role_permissions_permission_id",
            "permission_id",
        ),
        Index(
            "ix_identity_role_permissions_assigned_by_id",
            "assigned_by_id",
        ),
    )

    role_id: Mapped[UUID] = mapped_column(
        ForeignKey(_ROLE_FOREIGN_KEY, ondelete="RESTRICT"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey(_PERMISSION_FOREIGN_KEY, ondelete="RESTRICT"),
        primary_key=True,
    )
    assigned_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    role: Mapped[RoleModel] = relationship(back_populates="role_permissions")
    permission: Mapped[PermissionModel] = relationship(
        back_populates="role_permissions"
    )


class RefreshSessionModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    """One device-bound opaque refresh/session credential record."""

    __tablename__ = "identity_refresh_sessions"
    __table_args__ = (
        CheckConstraint(
            "refresh_token_hash ~ '^[0-9a-f]{64}$'",
            name="refresh_token_hash_sha256",
        ),
        CheckConstraint(
            "length(btrim(device_name)) BETWEEN 1 AND 120",
            name="device_name_length",
        ),
        CheckConstraint(
            "length(user_agent) BETWEEN 1 AND 1024",
            name="user_agent_length",
        ),
        CheckConstraint(
            "expires_at > last_activity_at",
            name="expiry_after_activity",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "ix_identity_refresh_sessions_refresh_token_hash",
            "refresh_token_hash",
            unique=True,
        ),
        Index(
            "ix_identity_refresh_sessions_user_id",
            "user_id",
        ),
        Index(
            "ix_identity_refresh_sessions_user_active",
            "user_id",
            "expires_at",
            postgresql_where=text("NOT is_revoked"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    browser: Mapped[str | None] = mapped_column(String(120), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    user_agent: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    user: Mapped[UserModel] = relationship(back_populates="refresh_sessions")


class PasswordHistoryModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "identity_password_history"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "password_hash",
            name="uq_identity_password_history_user_hash",
        ),
        CheckConstraint(_ARGON2ID_HASH_CHECK, name="password_hash_argon2id"),
        Index(
            "ix_identity_password_history_user_created",
            "user_id",
            "created_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="password_history")


class LoginAttemptModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "identity_login_attempts"
    __table_args__ = (
        CheckConstraint(
            "email = lower(btrim(email)) AND length(email) BETWEEN 3 AND 320",
            name="email_normalized",
        ),
        CheckConstraint(
            "success OR (reason IS NOT NULL AND "
            "length(btrim(reason)) BETWEEN 1 AND 100)",
            name="failed_reason_present",
        ),
        Index(
            "ix_identity_login_attempts_occurred_at",
            "occurred_at",
        ),
        Index(
            "ix_identity_login_attempts_email_occurred",
            "email",
            "occurred_at",
        ),
        Index(
            "ix_identity_login_attempts_ip_occurred",
            "ip_address",
            "occurred_at",
        ),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True)


class EmailVerificationTokenModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "identity_email_verification_tokens"
    __table_args__ = (
        CheckConstraint(_SHA256_HASH_CHECK, name="token_hash_sha256"),
        Index(
            "ix_identity_email_verification_tokens_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_identity_email_verification_tokens_user_expiry",
            "user_id",
            "expires_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="email_verification_tokens")


class PasswordResetTokenModel(UuidPrimaryKeyMixin, Base):
    __tablename__ = "identity_password_reset_tokens"
    __table_args__ = (
        CheckConstraint(_SHA256_HASH_CHECK, name="token_hash_sha256"),
        Index(
            "ix_identity_password_reset_tokens_token_hash",
            "token_hash",
            unique=True,
        ),
        Index(
            "ix_identity_password_reset_tokens_user_expiry",
            "user_id",
            "expires_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(_USER_FOREIGN_KEY, ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[UserModel] = relationship(back_populates="password_reset_tokens")
