from __future__ import annotations

from time import perf_counter
from typing import cast

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_REQUESTS = Counter(
    "fashion_network_http_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status_code"),
)
HTTP_REQUEST_DURATION = Histogram(
    "fashion_network_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
DEPENDENCY_UP = Gauge(
    "fashion_network_dependency_up",
    "Whether an application dependency passed its latest readiness check.",
    ("dependency",),
)
DEPENDENCY_CHECK_DURATION = Histogram(
    "fashion_network_dependency_check_duration_seconds",
    "Dependency readiness check duration in seconds.",
    ("dependency",),
)
DATABASE_POOL_SIZE = Gauge(
    "fashion_network_database_pool_size",
    "Configured SQLAlchemy connection pool size.",
)
DATABASE_POOL_CHECKED_IN = Gauge(
    "fashion_network_database_pool_checked_in",
    "Idle SQLAlchemy pool connections.",
)
DATABASE_POOL_CHECKED_OUT = Gauge(
    "fashion_network_database_pool_checked_out",
    "Checked-out SQLAlchemy pool connections.",
)
DATABASE_POOL_OVERFLOW = Gauge(
    "fashion_network_database_pool_overflow",
    "Current SQLAlchemy overflow connections.",
)
DATABASE_QUERY_DURATION = Histogram(
    "fashion_network_database_query_duration_seconds",
    "SQL statement duration by operation.",
    ("operation",),
)
WORKER_UP = Gauge(
    "fashion_network_worker_up",
    "Worker availability placeholder; worker exporters set this in Phase 2.",
)
WORKER_ACTIVE_TASKS = Gauge(
    "fashion_network_worker_active_tasks",
    "Active worker task placeholder; worker exporters set this in Phase 2.",
)
AUTHENTICATION_SUCCEEDED = Counter(
    "fashion_network_authentication_succeeded_total",
    "Successful identity authentications.",
)
AUTHENTICATION_FAILED = Counter(
    "fashion_network_authentication_failed_total",
    "Failed identity authentication attempts.",
)
AUTHENTICATION_REFRESHED = Counter(
    "fashion_network_authentication_refresh_total",
    "Successfully rotated refresh credentials.",
)
AUTHENTICATION_REFRESH_REUSE = Counter(
    "fashion_network_authentication_refresh_reuse_total",
    "Detected reuse of revoked refresh credentials.",
)
AUTHENTICATION_LOGOUT = Counter(
    "fashion_network_authentication_logout_total",
    "Completed current-session and all-session logout operations.",
)
SESSION_ACTIVE = Gauge(
    "fashion_network_identity_sessions_active",
    "Current active, unexpired identity sessions.",
)
SESSION_REVOKED = Gauge(
    "fashion_network_identity_sessions_revoked",
    "Current retained revoked identity sessions.",
)
SESSION_CLEANUP_EXECUTIONS = Counter(
    "fashion_network_identity_session_cleanup_executions_total",
    "Completed session-retention cleanup executions.",
)
SESSION_REVOCATIONS = Counter(
    "fashion_network_identity_session_revocations_total",
    "Sessions revoked through session-management operations.",
)
AUTHORIZATION_CHECKS = Counter(
    "fashion_network_identity_authorization_checks_total",
    "Completed identity authorization decisions.",
)
AUTHORIZATION_DENIED = Counter(
    "fashion_network_identity_authorization_denied_total",
    "Denied identity authorization decisions.",
)
PERMISSION_CACHE_HITS = Counter(
    "fashion_network_identity_permission_cache_hits_total",
    "Permission resolution cache hits.",
)
PERMISSION_CACHE_MISSES = Counter(
    "fashion_network_identity_permission_cache_misses_total",
    "Permission resolution cache misses.",
)
PASSWORD_CHANGES = Counter(
    "fashion_network_identity_password_change_total",
    "Completed account password changes.",
)
PASSWORD_RESETS = Counter(
    "fashion_network_identity_password_reset_total",
    "Completed account password resets.",
)
EMAIL_VERIFICATIONS = Counter(
    "fashion_network_identity_email_verification_total",
    "Completed account email verifications.",
)
ACCOUNT_LOCKOUTS = Counter(
    "fashion_network_identity_account_lockouts_total",
    "Applied progressive account lockouts.",
)
SECURITY_EVENTS = Counter(
    "fashion_network_identity_security_events_total",
    "Published account-security events.",
)
ACCOUNT_SECURITY_CLEANUP_EXECUTIONS = Counter(
    "fashion_network_identity_account_security_cleanup_executions_total",
    "Completed account-security cleanup runs.",
)
ACCOUNT_SECURITY_CLEANUP_RECORDS = Counter(
    "fashion_network_identity_account_security_cleanup_records_total",
    "Expired tokens deleted and expired account locks cleared.",
)
STORES_CREATED = Counter(
    "fashion_network_stores_created_total",
    "Created Store aggregates.",
)
STORES_ACTIVE = Gauge(
    "fashion_network_stores_active_total",
    "Current active, non-deleted stores.",
)
STORES_VERIFIED = Gauge(
    "fashion_network_stores_verified_total",
    "Current verified, non-deleted stores.",
)
STORE_VERIFICATION_SUBMITTED = Counter(
    "fashion_network_store_verification_submitted_total",
    "Store verification submissions, including reopened submissions.",
)
STORE_VERIFICATION_APPROVED = Counter(
    "fashion_network_store_verification_approved_total",
    "Approved Store verifications.",
)
STORE_VERIFICATION_REJECTED = Counter(
    "fashion_network_store_verification_rejected_total",
    "Rejected Store verifications.",
)
STORE_VERIFICATION_PENDING = Gauge(
    "fashion_network_store_verification_pending_total",
    "Current submitted or in-review Store verifications.",
)
STORE_MEMBERS = Gauge(
    "fashion_network_store_members_total",
    "Current active or suspended Store memberships.",
)
STORE_MEDIA_UPLOADS = Counter(
    "fashion_network_store_media_upload_total",
    "Completed Store media uploads.",
)
STORE_MEDIA_DELETES = Counter(
    "fashion_network_store_media_delete_total",
    "Completed Store media soft deletions.",
)
STORE_MEDIA_BYTES = Counter(
    "fashion_network_store_media_bytes_total",
    "Validated Store media bytes uploaded.",
)
STORE_MEDIA_FAILURES = Counter(
    "fashion_network_store_media_failures_total",
    "Rejected or failed Store media operations.",
)
STORE_MEMBER_INVITATIONS = Counter(
    "fashion_network_store_member_invitations_total",
    "Store membership invitations created.",
)
STORE_MEMBER_ACCEPTANCES = Counter(
    "fashion_network_store_member_acceptances_total",
    "Store membership invitations accepted.",
)
STORE_MEMBER_REMOVALS = Counter(
    "fashion_network_store_member_removals_total",
    "Store memberships removed.",
)
STORE_HOURS_UPDATES = Counter(
    "fashion_network_store_hours_updates_total",
    "Completed Store operating-hours mutations.",
)
STORE_HOURS_QUERIES = Counter(
    "fashion_network_store_hours_queries_total",
    "Completed Store operating-hours and business-status queries.",
)
STORE_OPEN = Counter(
    "fashion_network_store_open_total",
    "Store status calculations that resolved to open.",
)
STORE_CLOSED = Counter(
    "fashion_network_store_closed_total",
    "Store status calculations that resolved to closed.",
)
STORE_METRIC_EVENTS = Counter(
    "fashion_network_store_metric_events_total",
    "Store operational metric events recorded.",
)
STORE_DAILY_UPDATES = Counter(
    "fashion_network_store_daily_updates_total",
    "Store daily metric aggregates created or updated.",
)
STORE_STORAGE_BYTES = Gauge(
    "fashion_network_store_storage_bytes",
    "Latest observed active Store media bytes.",
)
STORE_PROFILE_VIEWS = Counter(
    "fashion_network_store_profile_views_total",
    "Store profile view metric events recorded.",
)
STORE_SEARCH_QUERIES = Counter(
    "fashion_network_store_search_queries_total",
    "Public Store search and autocomplete queries.",
)
STORE_SEARCH_RESULTS = Counter(
    "fashion_network_store_search_results_total",
    "Public Store search results returned.",
)
STORE_SEARCH_INDEX_UPDATES = Counter(
    "fashion_network_store_search_index_updates_total",
    "Successful Store search index updates.",
)
STORE_SEARCH_FAILURES = Counter(
    "fashion_network_store_search_failures_total",
    "Store search provider or indexing failures.",
)

WORKER_UP.set(0)
WORKER_ACTIVE_TASKS.set(0)
SESSION_ACTIVE.set(0)
SESSION_REVOKED.set(0)
STORES_ACTIVE.set(0)
STORES_VERIFIED.set(0)
STORE_VERIFICATION_PENDING.set(0)
STORE_MEMBERS.set(0)


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    if isinstance(route, Route):
        return route.path
    return "unmatched"


class MetricsMiddleware:
    """Record low-cardinality HTTP RED metrics."""

    def __init__(self, app: ASGIApp, *, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            route = _route_template(scope)
            method = cast(str, scope["method"])
            HTTP_REQUESTS.labels(method, route, str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method, route).observe(
                perf_counter() - started
            )


def update_database_pool_metrics(engine: AsyncEngine) -> None:
    """Snapshot QueuePool diagnostics without exposing connection details."""
    pool = cast(QueuePool, engine.sync_engine.pool)
    DATABASE_POOL_SIZE.set(pool.size())
    DATABASE_POOL_CHECKED_IN.set(pool.checkedin())
    DATABASE_POOL_CHECKED_OUT.set(pool.checkedout())
    DATABASE_POOL_OVERFLOW.set(pool.overflow())


def metrics_response(request: Request) -> Response:
    """Render the Prometheus exposition format."""
    manager = getattr(request.app.state, "database", None)
    if manager is not None:
        update_database_pool_metrics(manager.engine)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
