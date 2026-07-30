from __future__ import annotations

from celery import signals

from app.observability.metrics import WORKER_UP
from app.observability.sentry import capture_exception


def _task_failure(
    *,
    exception: BaseException | None = None,
    **_kwargs: object,
) -> None:
    if exception is not None:
        capture_exception(exception)


def _worker_ready(**_kwargs: object) -> None:
    WORKER_UP.set(1)


def _worker_shutdown(**_kwargs: object) -> None:
    WORKER_UP.set(0)


def install_worker_observability() -> None:
    """Connect business-neutral worker lifecycle and failure diagnostics."""
    signals.task_failure.connect(_task_failure, weak=False)
    signals.worker_ready.connect(_worker_ready, weak=False)
    signals.worker_shutdown.connect(_worker_shutdown, weak=False)
