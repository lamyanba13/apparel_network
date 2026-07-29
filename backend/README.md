# Backend foundation

The backend is a Python 3.13 FastAPI modular monolith managed by Poetry.

Phase 1.1 exposes only `GET /health`. Feature modules are empty boundary packages; database, authentication, events, background workers, and integrations are intentionally not implemented.

Use `poetry install`, then run `poetry run uvicorn app.main:app --reload` from this directory.

