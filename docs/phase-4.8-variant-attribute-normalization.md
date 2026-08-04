# Phase 4.8 — Variant Attribute Normalization & Transactional Outbox

Status: implemented; validation pending final approval

Phase 4.8 fulfills [ADR 0010](adr/0010-product-variant-mvp-deferral.md) by
replacing the temporary Product Variant JSONB attribute map with controlled,
Store-owned attribute definitions and values. The existing Product Variant
request and response shape remains compatible, but persistence and uniqueness
now use normalized value identities.

## Architecture

The Products bounded context retains its Domain, Application, Infrastructure,
API, Persistence, Events, Metrics, Tests, and Documentation layers.
Repositories flush only; the FastAPI request dependency owns commit and
rollback. Attribute and Variant ownership is resolved through the existing
Identity authorization and Store ownership chain, and cross-Store resources
return `404 Not Found`.

## Persistence

Migration `4b6c8e0a2d35_normalize_variant_attributes.py` creates:

- `product_attributes`, containing UUIDv7 identity, Store ownership, type,
  lifecycle, display/filter flags, ordering, optimistic version, audit fields,
  and soft-deletion metadata;
- `product_attribute_values`, containing the controlled values for an
  attribute, canonical slugs, ordering, optimistic version, and timestamps;
- `product_variant_attribute_values`, containing normalized Variant-to-value
  assignments with optimistic version and timestamps;
- `event_outbox`, containing identifier-only Variant events, publication state,
  retry count, optimistic version, and indexes for dispatch scans.

PostgreSQL enforces Store-scoped attribute slugs, attribute-scoped value slugs,
unique Variant/value assignments, positive versions, valid lifecycle deletion,
and non-negative ordering and retry counts. The migration backfills existing
JSONB values, rebuilds deterministic signatures from ordered value UUIDs, and
then removes `product_variants.attributes`. Downgrade reconstructs the legacy
map and signature before removing the normalized tables.

## Attribute model and lifecycle

Supported types are `text`, `number`, `boolean`, `date`, `color`, `size`, and
`enum`. Attributes are created `active` and may be archived, but archived
attributes cannot be reactivated or receive new values. Attribute deletion is
a soft archive with audit attribution. Values validate against their attribute
type; an assigned value cannot be deleted.

Attribute and value updates require the current optimistic version. Duplicate
Store slugs, duplicate value slugs, and duplicate case-insensitive values are
rejected with `409 Conflict`.

## Variant normalization

Product Variant create and update continue accepting the Phase 4.4 canonical
attribute map. Each key resolves to an active Store-owned attribute slug and
each value resolves to one of its controlled values. Unmapped attributes are
rejected rather than persisted as free-form data.

Variant combinations remain unique per Product. The signature is SHA-256 over
the canonically ordered set of attribute-value UUIDs, so display-name or value
text changes do not alter combination identity. Assignment prevents a second
value for the same attribute and removal cannot leave a Variant without an
attribute. Assignment and removal use the Variant optimistic version.

## Transactional outbox

Variant creation, update, archive, deletion, assignment, and removal append an
`event_outbox` row through `OutboxService` in the same SQLAlchemy session and
database transaction as the aggregate mutation. No direct publication occurs
in this phase. A future dispatcher will claim pending rows and provide
at-least-once delivery; consumers must remain idempotent.

The event payload contains only aggregate, Store, Product, and Variant IDs,
the resulting version, and timestamp. Outbox rows begin with `pending` status,
zero retries, and no publication timestamp.

## API and authorization

Attribute APIs:

- `POST /api/v1/attributes`
- `GET /api/v1/attributes`
- `PATCH /api/v1/attributes/{id}`
- `DELETE /api/v1/attributes/{id}`
- `POST /api/v1/attributes/{id}/values`
- `PATCH /api/v1/attribute-values/{id}`
- `DELETE /api/v1/attribute-values/{id}`

Variant assignment APIs:

- `POST /api/v1/variants/{id}/attributes`
- `GET /api/v1/variants/{id}/attributes`
- `DELETE /api/v1/variants/{id}/attributes/{value_id}`

Permissions are `attribute:create`, `attribute:view`, `attribute:update`, and
`attribute:assign`. The generated OpenAPI contract documents the routes,
request and response schemas, Bearer authentication, permission metadata, and
conflict/not-found responses.

## Events and metrics

Domain events are `VariantCreated`, `VariantUpdated`, `VariantDeleted`,
`VariantAttributeAssigned`, `VariantAttributeRemoved`, and `VariantArchived`.
They are persisted under stable `product_variant.*` event names.

Low-cardinality counters are:

- `fashion_network_attribute_created_total`;
- `fashion_network_attribute_value_created_total`;
- `fashion_network_variant_attribute_assigned_total`;
- `fashion_network_outbox_written_total`.

## Scope boundary

This phase does not implement an outbox dispatcher, search projection,
localization content, Cart, Checkout, Orders, or new Inventory/Pricing/Identity
behavior. It changes only how Product Variant attributes and Variant events are
persisted.
