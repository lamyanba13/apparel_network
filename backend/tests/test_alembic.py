from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.database.metadata import metadata
from app.modules.identity.infrastructure.persistence import models as identity_models
from app.modules.stores.infrastructure.persistence import models as store_models

BACKEND_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_REVISION = "b6d38dd509e1"
SESSION_LINEAGE_REVISION = "eb3079e2bb7e"
SESSION_RISK_REVISION = "a9c2cc1d183e"
SESSION_LIFECYCLE_REVISION = "d41f63a709b2"
AUTHORIZATION_REVISION = "f25a7c19e4d0"
ACCOUNT_SECURITY_REVISION = "c3d91e7a4b62"
STORE_DOMAIN_REVISION = "d48004d70e46"
STORE_VERIFICATION_REVISION = "0f7538229016"
STORE_MEMBERSHIP_REVISION = "47f0ff7d40b8"
STORE_MEDIA_REVISION = "2eb2bce458d5"
STORE_OPERATING_HOURS_REVISION = "077498dfaa91"
STORE_ANALYTICS_REVISION = "0f01b7088f73"
CATALOG_REVISION = "a91c7d4e2f10"
CATALOG_METADATA_REVISION = "b72e8d19c4f1"
PRODUCT_REVISION = "c83f1a9e2d04"
TAXONOMY_REVISION = "d94e2f7a1b05"
COLLECTION_TYPE_REVISION = "e12f4a6b8c90"
PRODUCT_MEDIA_REVISION = "f43b2c1d9e80"
PRODUCT_VARIANTS_REVISION = "697a9e0d3c1b"
INVENTORY_REVISION = "1d2e3f4a5b6c"
PRICING_REVISION = "2f4a6c8e0b12"
PRICE_LIST_REVISION = "3a5b7d9f1c24"
VARIANT_NORMALIZATION_REVISION = "4b6c8e0a2d35"
CART_REVISION = "5c7d9f1a3b46"
CHECKOUT_REVISION = "6d8e0f2a4c57"
ORDER_REVISION = "7e9f1a3b5d68"
PAYMENT_REVISION = "8f0a2b4c6d79"
RESERVATION_REVISION = "9a1b3c5d7e80"
SHIPMENT_REVISION = "aa2c4d6e8f91"
IDENTITY_TABLES = {
    "identity_email_verification_tokens",
    "identity_login_attempts",
    "identity_password_history",
    "identity_password_reset_tokens",
    "identity_permissions",
    "identity_refresh_sessions",
    "identity_role_permissions",
    "identity_roles",
    "identity_user_roles",
    "identity_users",
}
STORE_TABLES = {
    "store_daily_metrics",
    "store_media",
    "stores",
    "store_memberships",
    "store_operating_hours",
    "store_metric_events",
    "store_verifications",
}
CATALOG_TABLES = {"catalogs"}
PRODUCT_TABLES = {"products", "product_variants"}
INVENTORY_TABLES = {"inventory_items"}
PRICING_TABLES = {"product_prices", "price_lists", "price_list_assignments"}
ATTRIBUTE_TABLES = {
    "product_attributes",
    "product_attribute_values",
    "product_variant_attribute_values",
    "event_outbox",
}
CART_TABLES = {"shopping_carts", "shopping_cart_items"}
CHECKOUT_TABLES = {"checkout_sessions", "checkout_session_items"}
ORDER_TABLES = {"orders", "order_items"}
PAYMENT_TABLES = {"payment_intents", "payment_transactions"}
RESERVATION_TABLES = {
    "inventory_reservations",
    "inventory_reservation_items",
}
SHIPMENT_TABLES = {"shipments", "shipment_packages", "shipment_tracking_events"}
TAXONOMY_TABLES = {
    "categories",
    "product_categories",
    "collections",
    "collection_products",
}
PRODUCT_MEDIA_TABLES = {"product_media"}


def test_alembic_upgrades_application_schema_without_drift(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        config = Config(BACKEND_ROOT / "alembic.ini")
        script = ScriptDirectory.from_config(config)

        command.upgrade(config, "head")

        assert identity_models is not None
        assert store_models is not None
        assert IDENTITY_TABLES.issubset(metadata.tables)
        assert STORE_TABLES.issubset(metadata.tables)
        assert CATALOG_TABLES.issubset(metadata.tables)
        assert PRODUCT_TABLES.issubset(metadata.tables)
        assert INVENTORY_TABLES.issubset(metadata.tables)
        assert PRICING_TABLES.issubset(metadata.tables)
        assert ATTRIBUTE_TABLES.issubset(metadata.tables)
        assert CART_TABLES.issubset(metadata.tables)
        assert CHECKOUT_TABLES.issubset(metadata.tables)
        assert ORDER_TABLES.issubset(metadata.tables)
        assert PAYMENT_TABLES.issubset(metadata.tables)
        assert RESERVATION_TABLES.issubset(metadata.tables)
        assert SHIPMENT_TABLES.issubset(metadata.tables)
        assert TAXONOMY_TABLES.issubset(metadata.tables)
        assert PRODUCT_MEDIA_TABLES.issubset(metadata.tables)
        assert script.get_heads() == [SHIPMENT_REVISION]
        assert {
            path.stem
            for path in (BACKEND_ROOT / "migrations" / "versions").glob("*.py")
        } == {
            f"{IDENTITY_REVISION}_create_identity_persistence",
            f"{SESSION_LINEAGE_REVISION}_add_refresh_session_rotation_lineage",
            f"{SESSION_RISK_REVISION}_reserve_session_risk_metadata",
            f"{SESSION_LIFECYCLE_REVISION}_add_session_lifecycle_metadata",
            f"{AUTHORIZATION_REVISION}_seed_authorization_foundation",
            f"{ACCOUNT_SECURITY_REVISION}_add_account_security_state",
            f"{STORE_DOMAIN_REVISION}_create_store_domain",
            f"{STORE_VERIFICATION_REVISION}_create_store_verification_workflow",
            f"{STORE_MEMBERSHIP_REVISION}_create_store_membership_management",
            f"{STORE_MEDIA_REVISION}_create_store_media_platform",
            f"{STORE_OPERATING_HOURS_REVISION}_create_store_operating_hours",
            f"{STORE_ANALYTICS_REVISION}_create_store_analytics_foundation",
            f"{CATALOG_REVISION}_create_catalogs",
            f"{CATALOG_METADATA_REVISION}_add_catalog_lifecycle_metadata",
            f"{PRODUCT_REVISION}_create_products",
            f"{TAXONOMY_REVISION}_create_product_taxonomy",
            f"{COLLECTION_TYPE_REVISION}_add_collection_type",
            f"{PRODUCT_MEDIA_REVISION}_create_product_media",
            f"{PRODUCT_VARIANTS_REVISION}_create_product_variants",
            f"{INVENTORY_REVISION}_create_inventory",
            f"{PRICING_REVISION}_create_product_prices",
            f"{PRICE_LIST_REVISION}_create_price_lists",
            f"{VARIANT_NORMALIZATION_REVISION}_normalize_variant_attributes",
            f"{CART_REVISION}_create_carts",
            f"{CHECKOUT_REVISION}_create_checkout_sessions",
            f"{ORDER_REVISION}_create_orders",
            f"{PAYMENT_REVISION}_create_payments",
            f"{RESERVATION_REVISION}_create_inventory_reservations",
            f"{SHIPMENT_REVISION}_create_shipments",
        }

        command.check(config)
    finally:
        get_settings.cache_clear()
