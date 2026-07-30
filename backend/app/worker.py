from celery import Celery

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
)
