from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings
from app.observability import configure_celery_telemetry, configure_sentry
from app.observability.worker import install_worker_observability

configure_sentry(settings)
configure_celery_telemetry(settings)
install_worker_observability()
celery_app = Celery("fashion_network", broker=settings.rabbitmq_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    control_queue_exclusive=True,
    enable_utc=True,
    event_queue_exclusive=True,
    result_backend=None,
    task_ignore_result=True,
    task_serializer="json",
    timezone="UTC",
    include=[
        "app.modules.stores.infrastructure.search_tasks",
        "app.modules.notifications.infrastructure.tasks",
    ],
    task_default_queue="store-search",
    task_queues=(
        Queue(
            "store-search",
            exchange=Exchange("store-search"),
            routing_key="store-search",
            queue_arguments={
                "x-dead-letter-exchange": "store-search-dlx",
                "x-dead-letter-routing-key": "store-search-dead-letter",
            },
        ),
        Queue(
            "notification-events",
            exchange=Exchange("notification-events"),
            routing_key="notification-events",
            queue_arguments={
                "x-dead-letter-exchange": "notification-events-dlx",
                "x-dead-letter-routing-key": "notification-events-dead-letter",
            },
        ),
        Queue(
            "notification-events-dead-letter",
            exchange=Exchange("notification-events-dlx"),
            routing_key="notification-events-dead-letter",
        ),
        Queue(
            "store-search-dead-letter",
            exchange=Exchange("store-search-dlx"),
            routing_key="store-search-dead-letter",
        ),
    ),
    task_routes={
        "stores.search.*": {
            "queue": "store-search",
            "routing_key": "store-search",
        },
        "notifications.*": {
            "queue": "notification-events",
            "routing_key": "notification-events",
        },
    },
)

from app.modules.stores.infrastructure import (  # noqa: E402,F401
    search_tasks as _search_tasks,
)
