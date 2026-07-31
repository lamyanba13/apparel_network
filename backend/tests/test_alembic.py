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
STORE_TABLES = {"stores", "store_verifications"}


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
        assert script.get_heads() == [STORE_VERIFICATION_REVISION]
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
        }

        command.check(config)
    finally:
        get_settings.cache_clear()
