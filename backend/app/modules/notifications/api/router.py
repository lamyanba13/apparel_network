from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.common.pagination import PageMetadata
from app.modules.identity.api.authorization import require_permission
from app.modules.identity.api.dependencies import CurrentIdentity
from app.modules.notifications.api.dependencies import (
    NotificationServiceDependency,
    NotificationTestServiceDependency,
)
from app.modules.notifications.api.schemas import (
    MarkReadRequest,
    NotificationListResponse,
    NotificationResponse,
    PreferenceResponse,
    PreferenceUpdateRequest,
    TestNotificationRequest,
)
from app.modules.notifications.application.schemas import (
    NotificationFilter,
    PreferenceUpdate,
    TestNotification,
)
from app.modules.notifications.domain import NotificationChannel

router = APIRouter(tags=["Notifications"])
_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "Authentication credentials are invalid"},
    403: {"description": "The identity lacks the required permission"},
    404: {"description": "Notification not found"},
}


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    dependencies=[require_permission("notification:view")],
    responses=_RESPONSES,
)
async def list_notifications(
    identity: CurrentIdentity,
    service: NotificationServiceDependency,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    channel: NotificationChannel | None = None,
    unread_only: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> NotificationListResponse:
    values, total = await service.list(
        identity.user.id,
        NotificationFilter(status_filter, channel, unread_only, offset, limit),
    )
    items = [NotificationResponse.model_validate(value) for value in values]
    return NotificationListResponse(
        items=items,
        page=PageMetadata(
            has_more=offset + len(items) < total,
            limit=limit,
            total=total,
            offset=offset,
        ),
    )


@router.get(
    "/notifications/preferences",
    response_model=PreferenceResponse,
    dependencies=[require_permission("notification:preferences")],
)
async def get_preferences(
    identity: CurrentIdentity, service: NotificationServiceDependency
) -> PreferenceResponse:
    return PreferenceResponse.model_validate(
        await service.preferences(identity.user.id)
    )


@router.patch(
    "/notifications/preferences",
    response_model=PreferenceResponse,
    dependencies=[require_permission("notification:preferences")],
    responses={409: {"description": "Version conflict"}},
)
async def update_preferences(
    payload: PreferenceUpdateRequest,
    identity: CurrentIdentity,
    service: NotificationServiceDependency,
) -> PreferenceResponse:
    values = payload.model_dump(exclude_unset=True, exclude={"version"})
    return PreferenceResponse.model_validate(
        await service.update_preferences(
            identity.user.id,
            PreferenceUpdate(values, payload.version, identity.user.id),
        )
    )


@router.post(
    "/notifications/test",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("notification:test")],
)
async def send_test_notification(
    payload: TestNotificationRequest,
    identity: CurrentIdentity,
    service: NotificationTestServiceDependency,
) -> NotificationResponse:
    return NotificationResponse.model_validate(
        await service.send(
            identity.user.id,
            TestNotification(
                payload.channel, payload.subject, payload.body, identity.user.id
            ),
        )
    )


@router.get(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    dependencies=[require_permission("notification:view")],
    responses=_RESPONSES,
)
async def get_notification(
    notification_id: UUID,
    identity: CurrentIdentity,
    service: NotificationServiceDependency,
) -> NotificationResponse:
    return NotificationResponse.model_validate(
        await service.detail(notification_id, identity.user.id)
    )


@router.patch(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    dependencies=[require_permission("notification:update")],
    responses={**_RESPONSES, 409: {"description": "Version conflict"}},
)
async def mark_notification_read(
    notification_id: UUID,
    payload: MarkReadRequest,
    identity: CurrentIdentity,
    service: NotificationServiceDependency,
) -> NotificationResponse:
    return NotificationResponse.model_validate(
        await service.mark_read(notification_id, identity.user.id, payload.version)
    )
