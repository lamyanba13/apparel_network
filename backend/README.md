# Backend foundation

The backend is a Python 3.13 FastAPI modular monolith managed by Poetry.

Phase 1.3 provides the shared asynchronous PostgreSQL foundation:

- SQLAlchemy 2.x typed declarative metadata;
- asyncpg engine and bounded connection pool;
- request-scoped `AsyncSession` dependency;
- rollback on failed request work and automatic session cleanup;
- lifespan startup validation and graceful pool disposal;
- database-aware `GET /health`;
- Alembic autogeneration wiring with no migration revisions yet;
- reusable UUIDv7, timestamp, selective soft-delete, audit, and optimistic
  version mixins.

No business models, business tables, authentication, users, stores, products,
inventory, or reservations are implemented.

From this directory:

```text
poetry install
poetry run alembic upgrade head
poetry run alembic check
poetry run uvicorn app.main:app --reload
```

The normal repository workflow runs these commands through Docker Compose; see
the root `README.md`.
