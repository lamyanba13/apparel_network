from app.modules.notifications.domain.models import NotificationChannel

DEFAULT_CHANNELS = frozenset({NotificationChannel.EMAIL, NotificationChannel.IN_APP})
DEFAULT_LANGUAGE = "en"

__all__ = ["DEFAULT_CHANNELS", "DEFAULT_LANGUAGE"]
