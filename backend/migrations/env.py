from __future__ import annotations

from logging.config import fileConfig

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Configure a future offline migration run."""
    raise RuntimeError("Database migrations are not enabled in Phase 1.1")


def run_migrations_online() -> None:
    """Configure a future online migration run."""
    raise RuntimeError("Database migrations are not enabled in Phase 1.1")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

