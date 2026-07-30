# ADR 0004: FastAPI for the Backend

- Date: 2026-07-30
- Status: Accepted

## Context

The backend needs typed HTTP contracts, asynchronous I/O support, generated OpenAPI documentation, dependency injection at the delivery boundary, and alignment with the selected Python ecosystem.

## Decision

Use FastAPI as the backend HTTP framework with Pydantic schemas and settings, Uvicorn as the ASGI server, SQLAlchemy for persistence, and an application factory for deterministic configuration and testing.

FastAPI is a delivery adapter. Route handlers validate and translate HTTP concerns, invoke application services, and map results to stable response contracts. Business rules do not reside in route handlers or depend directly on FastAPI.

## Alternatives considered

- Django with Django REST Framework: mature and productive, but includes a broader integrated framework than the selected foundation requires.
- NestJS or another Node.js backend: rejected to preserve the approved Python backend stack.
- Flask: lightweight, but would require more assembly for typing, validation, asynchronous contracts, and OpenAPI.

## Consequences

- Strong typing and generated API descriptions improve developer experience and contract testing.
- Framework convenience can blur architecture boundaries unless route handlers remain thin.
- Dependency and OpenAPI changes require compatibility tests.
- Asynchronous code must avoid blocking work in request processes.
