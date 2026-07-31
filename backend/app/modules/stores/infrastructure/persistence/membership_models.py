from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import (
    TimestampMixin,
    UuidPrimaryKeyMixin,
    VersionNumberMixin,
)
from app.modules.stores.domain import StoreMembershipRole, StoreMembershipStatus


class StoreMembershipModel(
    UuidPrimaryKeyMixin,
    TimestampMixin,
    VersionNumberMixin,
    Base,
):
    __tablename__ = "store_memberships"
    __table_args__ = (
        CheckConstraint(
            "("
            "status = 'pending' AND accepted_at IS NULL "
            "AND removed_at IS NULL AND invitation_expires_at IS NOT NULL"
            ") OR ("
            "status IN ('active', 'suspended') AND accepted_at IS NOT NULL "
            "AND removed_at IS NULL"
            ") OR ("
            "status IN ('declined', 'removed', 'expired') "
            "AND removed_at IS NOT NULL"
            ")",
            name="lifecycle_consistent",
        ),
        CheckConstraint(
            "(role = 'owner' AND status = 'active' "
            "AND accepted_at IS NOT NULL AND invitation_expires_at IS NULL) "
            "OR role <> 'owner'",
            name="owner_active",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index(
            "uq_store_memberships_active_owner",
            "store_id",
            unique=True,
            postgresql_where=text("role = 'owner' AND status = 'active'"),
        ),
        Index(
            "uq_store_memberships_live_user",
            "store_id",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('active', 'suspended')"),
        ),
        Index(
            "uq_store_memberships_pending_user",
            "store_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_store_memberships_store_status_created",
            "store_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_store_memberships_user_status",
            "user_id",
            "status",
        ),
        Index(
            "ix_store_memberships_pending_expiry",
            "invitation_expires_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[StoreMembershipRole] = mapped_column(
        Enum(
            StoreMembershipRole,
            name="store_membership_role",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[StoreMembershipStatus] = mapped_column(
        Enum(
            StoreMembershipStatus,
            name="store_membership_status",
            native_enum=False,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    invited_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("identity_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invitation_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
