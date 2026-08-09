from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.modules.stores.domain import StoreMembershipStatus
from app.modules.stores.infrastructure.persistence.membership_models import (
    StoreMembershipModel,
)
from app.modules.stores.infrastructure.persistence.models import StoreModel


def store_accessible_by(actor_id: UUID) -> ColumnElement[bool]:
    """Match a Store owner or an accepted active Store member."""
    return or_(
        StoreModel.owner_id == actor_id,
        exists(
            select(StoreMembershipModel.id).where(
                StoreMembershipModel.store_id == StoreModel.id,
                StoreMembershipModel.user_id == actor_id,
                StoreMembershipModel.status == StoreMembershipStatus.ACTIVE,
            )
        ),
    )
