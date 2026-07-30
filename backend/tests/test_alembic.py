from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.database.metadata import metadata

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_configuration_has_metadata_and_no_revisions(
    monkeypatch: MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.chdir(BACKEND_ROOT)
    monkeypatch.setenv("FASHION_NETWORK_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        config = Config(BACKEND_ROOT / "alembic.ini")
        script = ScriptDirectory.from_config(config)

        assert metadata.tables == {}
        assert script.get_heads() == []
        assert list((BACKEND_ROOT / "migrations" / "versions").glob("*.py")) == []

        command.check(config)
    finally:
        get_settings.cache_clear()
