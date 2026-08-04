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
CATALOGS_CREATED = Counter("fashion_network_catalog_created_total", "Catalogs created.")
CATALOGS_UPDATED = Counter("fashion_network_catalog_updated_total", "Catalogs updated.")
CATALOGS_DELETED = Counter("fashion_network_catalog_deleted_total", "Catalogs deleted.")
CATALOGS_ARCHIVED = Counter(
    "fashion_network_catalog_archived_total", "Catalogs archived."
)
PRODUCTS_CREATED = Counter("fashion_network_product_created_total", "Products created.")
PRODUCTS_UPDATED = Counter("fashion_network_product_updated_total", "Products updated.")
PRODUCTS_DELETED = Counter("fashion_network_product_deleted_total", "Products deleted.")
PRODUCTS_ARCHIVED = Counter(
    "fashion_network_product_archived_total", "Products archived."
)
INVENTORY_CREATED = Counter(
    "fashion_network_inventory_created_total", "Inventory records created."
)
INVENTORY_UPDATED = Counter(
    "fashion_network_inventory_updated_total", "Inventory records updated."
)
INVENTORY_DELETED = Counter(
    "fashion_network_inventory_deleted_total", "Inventory records deleted."
)
INVENTORY_ADJUSTMENTS = Counter(
    "fashion_network_inventory_adjustments_total", "Inventory adjustments completed."
)
PRICES_CREATED = Counter(
    "fashion_network_price_created_total", "Product prices created."
)
PRICES_UPDATED = Counter(
    "fashion_network_price_updated_total", "Product prices updated."
)
PRICES_DELETED = Counter(
    "fashion_network_price_deleted_total", "Product prices deleted."
)
PRICES_ACTIVATED = Counter(
    "fashion_network_price_activated_total", "Product prices activated."
)
PRICE_LISTS_CREATED = Counter(
    "fashion_network_price_list_created_total", "Price Lists created."
)
PRICE_LISTS_UPDATED = Counter(
    "fashion_network_price_list_updated_total", "Price Lists updated."
)
PRICES_ASSIGNED = Counter(
    "fashion_network_price_assigned_total", "Prices assigned to Price Lists."
)
PRICES_RESOLVED = Counter(
    "fashion_network_price_resolved_total", "Prices successfully resolved."
)
PRICE_RESOLUTION_DURATION = Histogram(
    "fashion_network_price_resolution_duration_seconds",
    "Price resolution duration in seconds.",
)
PRODUCT_VARIANTS_CREATED = Counter(
    "fashion_network_product_variant_created_total", "Product variants created."
)
PRODUCT_VARIANTS_UPDATED = Counter(
    "fashion_network_product_variant_updated_total", "Product variants updated."
)
PRODUCT_VARIANTS_DELETED = Counter(
    "fashion_network_product_variant_deleted_total", "Product variants deleted."
)
ATTRIBUTES_CREATED = Counter(
    "fashion_network_attribute_created_total", "Product Attributes created."
)
ATTRIBUTE_VALUES_CREATED = Counter(
    "fashion_network_attribute_value_created_total",
    "Product Attribute Values created.",
)
VARIANT_ATTRIBUTES_ASSIGNED = Counter(
    "fashion_network_variant_attribute_assigned_total",
    "Attribute Values assigned to Product Variants.",
)
OUTBOX_WRITTEN = Counter(
    "fashion_network_outbox_written_total", "Transactional outbox records written."
)
CARTS_CREATED = Counter("fashion_network_cart_created_total", "Shopping Carts created.")
CART_ITEMS_ADDED = Counter(
    "fashion_network_cart_item_added_total", "Shopping Cart Items added."
)
CART_ITEMS_REMOVED = Counter(
    "fashion_network_cart_item_removed_total", "Shopping Cart Items removed."
)
CARTS_CHECKED_OUT = Counter(
    "fashion_network_cart_checkout_total", "Shopping Carts checked out."
)
CARTS_ABANDONED = Counter(
    "fashion_network_cart_abandoned_total", "Shopping Carts abandoned."
)
CHECKOUTS_CREATED = Counter(
    "fashion_network_checkout_created_total", "Checkout Sessions created."
)
CHECKOUTS_CONFIRMED = Counter(
    "fashion_network_checkout_confirmed_total", "Checkout Sessions confirmed."
)
CHECKOUTS_CANCELLED = Counter(
    "fashion_network_checkout_cancelled_total", "Checkout Sessions cancelled."
)
CHECKOUTS_EXPIRED = Counter(
    "fashion_network_checkout_expired_total", "Checkout Sessions expired."
)
ORDERS_CREATED = Counter("fashion_network_order_created_total", "Orders created.")
ORDERS_CONFIRMED = Counter("fashion_network_order_confirmed_total", "Orders confirmed.")
ORDERS_CANCELLED = Counter("fashion_network_order_cancelled_total", "Orders cancelled.")
PAYMENTS_CREATED = Counter(
    "fashion_network_payment_created_total", "Payment Intents created."
)
PAYMENTS_AUTHORIZED = Counter(
    "fashion_network_payment_authorized_total", "Payments authorized."
)
PAYMENTS_CAPTURED = Counter(
    "fashion_network_payment_captured_total", "Payments captured."
)
PAYMENTS_FAILED = Counter("fashion_network_payment_failed_total", "Payments failed.")
PAYMENTS_CANCELLED = Counter(
    "fashion_network_payment_cancelled_total", "Payments cancelled."
)
PAYMENT_PROCESSING_DURATION = Histogram(
    "fashion_network_payment_processing_duration_seconds",
    "Time spent invoking the configured Payment gateway.",
)
RESERVATIONS_CREATED = Counter(
    "fashion_network_reservation_created_total", "Reservations created."
)
RESERVATIONS_CONSUMED = Counter(
    "fashion_network_reservation_consumed_total", "Reservations consumed."
)
RESERVATIONS_RELEASED = Counter(
    "fashion_network_reservation_released_total", "Reservations released."
)
RESERVATIONS_EXPIRED = Counter(
    "fashion_network_reservation_expired_total", "Reservations expired."
)
RESERVATION_DURATION = Histogram(
    "fashion_network_reservation_duration_seconds",
    "Lifetime of Reservations before a terminal transition.",
)
SHIPMENTS_CREATED = Counter(
    "fashion_network_shipment_created_total", "Shipments created."
)
SHIPMENTS_PACKED = Counter("fashion_network_shipment_packed_total", "Shipments packed.")
SHIPMENTS_SHIPPED = Counter(
    "fashion_network_shipment_shipped_total", "Shipments shipped."
)
SHIPMENTS_DELIVERED = Counter(
    "fashion_network_shipment_delivered_total", "Shipments delivered."
)
SHIPMENTS_CANCELLED = Counter(
    "fashion_network_shipment_cancelled_total", "Shipments cancelled."
)
DELIVERY_DURATION = Histogram(
    "fashion_network_delivery_duration_seconds",
    "Time from shipment dispatch to delivery.",
)
CATEGORIES_CREATED = Counter(
    "fashion_network_category_created_total", "Categories created."
)
CATEGORIES_DELETED = Counter(
    "fashion_network_category_deleted_total", "Categories deleted."
)
COLLECTIONS_CREATED = Counter(
    "fashion_network_collection_created_total", "Collections created."
)
COLLECTIONS_DELETED = Counter(
    "fashion_network_collection_deleted_total", "Collections deleted."
)
PRODUCT_CATEGORY_ASSIGNMENTS = Counter(
    "fashion_network_product_category_assignments_total",
    "Product category assignments.",
)
PRODUCT_COLLECTION_ASSIGNMENTS = Counter(
    "fashion_network_product_collection_assignments_total",
    "Product collection assignments.",
)
PRODUCT_MEDIA_UPLOADS = Counter(
    "fashion_network_product_media_upload_total", "Product media uploads."
)
PRODUCT_MEDIA_DELETES = Counter(
    "fashion_network_product_media_delete_total", "Product media deletions."
)
PRODUCT_MEDIA_BYTES = Counter(
    "fashion_network_product_media_bytes_total", "Product media bytes."
)
PRODUCT_MEDIA_FAILURES = Counter(
    "fashion_network_product_media_failures_total", "Product media failures."
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
