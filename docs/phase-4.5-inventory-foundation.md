# Phase 4.5 — Inventory Foundation

Status: implemented, pending review

Inventory establishes PostgreSQL as the authoritative record for one Product
Variant at one Store. `inventory_items` stores on-hand, reserved, and derived
available quantities with database constraints, optimistic locking, soft
deletion, tenant ownership checks, and identifier-only domain events.

The API exposes create, list, detail, update, and soft-delete operations at
`/api/v1/inventory`, reusing `catalog:view` and `catalog:update`. Reservations,
movements, multiple locations, search integration, and preorder behaviour are
explicitly outside this foundation.
