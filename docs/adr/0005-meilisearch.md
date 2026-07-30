# ADR 0005: Meilisearch for Search Projections

- Date: 2026-07-30
- Status: Accepted

## Context

Customers must search inventory across participating stores with low latency and relevant text matching. PostgreSQL is authoritative, but the public discovery workload benefits from a purpose-built search index.

## Decision

Use Meilisearch as a rebuildable search projection. PostgreSQL remains the source of truth for products, stores, availability, and future reservation state.

Index updates will be asynchronous and idempotent. The production design must include reconciliation and full reindex procedures before search-backed business functionality is released. Search results must never directly mutate authoritative state.

## Alternatives considered

- PostgreSQL full-text search: simpler operationally, but less aligned with the intended search experience and independent search tuning.
- Elasticsearch or OpenSearch: capable, but operationally heavier than required for the initial platform.
- A hosted search API: potentially lower operations burden, but introduces provider cost and lock-in before usage is known.

## Consequences

- Search can be tuned and scaled independently from transactional queries.
- Results are eventually consistent and the UI must tolerate short projection delays.
- Index settings, versioning, reindexing, and drift monitoring become operational responsibilities.
- Losing the index must be recoverable from PostgreSQL without losing business data.
