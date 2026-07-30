from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.database.metadata import metadata
from app.modules.identity.infrastructure.persistence import models as identity_models

BACKEND_ROOT = Path(__file__).resolve().parents[1]
IDENTITY_REVISION = "b6d38dd509e1"
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


def test_alembic_upgrades_identity_schema_without_drift(
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
        assert IDENTITY_TABLES.issubset(metadata.tables)
        assert script.get_heads() == [IDENTITY_REVISION]
        assert {
            path.stem
            for path in (BACKEND_ROOT / "migrations" / "versions").glob("*.py")
        } == {f"{IDENTITY_REVISION}_create_identity_persistence"}

        command.check(config)
    finally:
        get_settings.cache_clear()
