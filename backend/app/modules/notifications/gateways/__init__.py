from app.modules.notifications.gateways.null_gateway import NullNotificationGateway
from app.modules.notifications.gateways.protocols import (
    GatewayResult,
    NotificationGateway,
)

__all__ = ["GatewayResult", "NotificationGateway", "NullNotificationGateway"]
