# API Standards

## Scope

The FastAPI HTTP API is the authoritative client contract for the public frontend, dashboard, and approved integrations. These standards apply to synchronous HTTP endpoints. Asynchronous event contracts follow the architecture event rules.

## OpenAPI-first authority

`docs/api/openapi.yaml` is the design source of truth. Endpoint work begins with a reviewed contract change containing operation ID, authorization, parameters, schemas, response/error variants, examples, and requirement traceability. The backend implementation and generated TypeScript client conform to that artifact.

FastAPI's generated OpenAPI representation is retained as an implementation view. CI performs semantic comparison: undocumented paths/operations, incompatible schemas, missing error responses, security drift, or changed operation IDs fail the build. Formatting or harmless ordering differences do not.

## Base URL and versioning

- All endpoints use HTTPS in non-local environments.
- The initial path prefix is `/api/v1`.
- Major breaking changes require a new path version.
- Additive optional fields and new endpoints normally remain within the current major version.
- Clients MUST ignore unknown response fields.
- Removing or changing a field's meaning, narrowing accepted input, or changing authorization behavior in a client-breaking way requires versioning or a managed migration.
- Deprecated behavior is documented in the API changelog with migration guidance and a removal date. A minimum deprecation window is set before external integrations are accepted.

Versioning applies to representation contracts, not the internal module structure.

## Resource design

- Paths use plural nouns: `/stores`, `/products`, `/reservations`.
- Nested paths express true containment or action scope and remain shallow.
- Use HTTP methods semantically:
  - `GET` reads and is safe;
  - `POST` creates or invokes a non-idempotent-by-default command;
- `PATCH` applies a partial update;
  - `PUT` is reserved for full replacement or naturally idempotent setting where appropriate;
  - `DELETE` removes/cancels only when that is the clear resource semantics.
- Business transitions that are not CRUD use explicit command subresources, such as a reservation fulfillment command, and are documented as state transitions.
- Do not put sensitive data in URLs.
- Public, customer, store, and admin representations are separate when their exposed data differs.
- `PATCH` uses JSON Merge Patch semantics with `application/merge-patch+json` unless an endpoint documents an explicit command. JSON Patch is not supported initially.

## Identifiers and data formats

- External resource IDs are opaque strings, preferably UUID-compatible. Clients must not infer type, order, or count from them.
- Human-readable reservation references are display/search aids and never authorization credentials.
- Timestamps use RFC 3339/ISO 8601 with timezone, emitted in UTC using `Z`.
- Dates use `YYYY-MM-DD`.
- Enums use stable lowercase snake-case values and are documented.
- Quantities are integers with defined lower/upper bounds.
- Approved prices use decimal strings and a separate ISO 4217 currency code.
- Boolean values are true booleans.
- Missing, `null`, empty string, and empty collection have distinct documented meanings.

## Request rules

- JSON is the default body format.
- Request `Content-Type` and accepted response types are validated.
- Unknown fields MUST be rejected for P0 mutation payloads.
- JSON request bodies default to 1 MiB maximum; endpoint-specific lower limits are preferred. Media bytes use the signed upload path, never JSON/API proxying.
- Server-side validation is authoritative.
- Partial updates distinguish an omitted field from an explicit `null`.
- Clients send `X-Request-ID` only if it meets format policy; otherwise the system generates one.

## Response envelope

Successful single-resource responses return the resource directly unless metadata is required. Collections use a consistent shape:

```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  }
}
```

This JSON is a contract illustration, not application code.

Responses include:

- `X-Request-ID`;
- appropriate cache-control headers;
- deprecation headers when applicable;
- rate-limit headers for endpoints where clients need them.

Never return private exact stock in public product/search responses.

## Pagination

- Cursor pagination is the default for mutable or large collections.
- Cursors are opaque, signed or otherwise tamper-resistant where needed, and encode a deterministic sort boundary.
- Default and maximum page sizes are documented per endpoint and bounded globally.
- Collection defaults are 25 items and the global maximum is 100 unless a stricter endpoint contract applies. Bulk export/import uses asynchronous operations rather than oversized pages.
- Offset pagination MAY be used for small stable admin/reference collections when the trade-off is documented.
- Search pagination follows Meilisearch capability but the API hides provider-specific tokens where feasible.
- Every sort has a stable tie-breaker to avoid duplicate/missing items between pages.

## Filtering, sorting, and search

- Query parameters use documented field names; repeated values or comma-separated values are standardized once.
- Repeated query parameters represent multiple values (`size=M&size=L`); comma splitting is not performed because values may contain commas.
- Unsupported filters and sort values return a validation error rather than being ignored.
- Sort parameters use `sort=field` or `sort=-field`; only allowlisted fields are accepted and a stable opaque-ID tie-breaker is always applied.
- Search queries have minimum/maximum length and normalization rules.
- Search query text is trimmed and limited to 200 Unicode code points; an empty query is permitted only for explicitly documented browse behavior.
- Filter behavior is AND across different facet types and explicitly defined within the same facet.
- Response metadata MAY include applied filters and facet counts when supported.
- Search results are discovery hints; product detail and reservation operations revalidate PostgreSQL eligibility.

## Idempotency

Idempotency is required for reservation creation and other safely retryable high-impact commands.

- Client sends `Idempotency-Key` with a high-entropy value.
- Scope is authenticated actor plus endpoint/operation.
- The server stores key, canonical request fingerprint, status, and outcome reference for a documented TTL.
- Same key and same fingerprint returns the original logical result.
- Same key with different payload returns `409 Conflict` with a stable error code.
- Concurrent same-key requests serialize so only one operation takes effect.
- Provider or gateway retries do not bypass this behavior.

PATCH/PUT/DELETE operations must also be naturally idempotent where their semantics allow it.

## Optimistic concurrency

Resources vulnerable to lost updates SHOULD expose a version or ETag. Mutation clients submit `If-Match` or an expected version. A stale version returns `409` or `412` consistently, with enough safe information to reload. Inventory reservation itself uses server-side transactional locking, not client optimistic concurrency.

## Authentication and authorization

- Browser authentication uses the server-managed opaque session model in System Architecture.
- Session cookies are host-only, `Secure`, `HttpOnly`, and `SameSite=Lax`; state-changing requests require the session-bound CSRF control and allowed `Origin`.
- The public frontend and dashboard use their own same-origin API route/proxy and separate host-scoped sessions.
- Browser bearer tokens and long-lived JWT storage are not part of the first-release design.
- Every protected operation declares authentication plus required action/resource scope.
- Resource existence may be hidden with `404` when `403` would leak sensitive tenancy information; the policy must be consistent.
- Admin endpoints use an explicit `/admin` namespace and separate permissions.
- CORS uses an exact allowlist. Credentials and wildcard origins are never combined.

## Error model

Errors use `application/problem+json` based on RFC 9457-style problem details:

```json
{
  "type": "https://docs.example.invalid/problems/insufficient-availability",
  "title": "Insufficient availability",
  "status": 409,
  "code": "inventory.insufficient_availability",
  "detail": "The requested quantity is no longer available.",
  "instance": "/api/v1/reservations",
  "request_id": "opaque-request-id",
  "errors": [
    {
      "field": "lines[0].quantity",
      "code": "quantity_unavailable",
      "message": "Choose a lower quantity or another variant."
    }
  ]
}
```

Rules:

- `code` is stable and machine-readable.
- `detail` is safe for end users and does not contain internals.
- Field errors use stable field paths.
- Authentication errors do not reveal whether an account exists.
- Provider, SQL, storage, and stack-trace details are never returned.
- `request_id` supports help-desk correlation but grants no access.

## Status codes

| Code | Use |
|---|---|
| 200 | Successful read/update/command with response. |
| 201 | Resource created; include `Location` where useful. |
| 202 | Durable asynchronous work accepted, with status resource when user-visible. |
| 204 | Successful operation with no response body. |
| 400 | Malformed request outside structured field validation. |
| 401 | Missing/invalid authentication. |
| 403 | Authenticated but not permitted where disclosure is safe. |
| 404 | Resource absent or intentionally concealed. |
| 409 | State, uniqueness, idempotency, or availability conflict. |
| 412 | Failed explicit precondition/ETag policy. |
| 422 | Semantically invalid fields or payload. |
| 429 | Rate limit exceeded; include safe retry guidance. |
| 500 | Unexpected internal failure. |
| 502/503/504 | Dependency or temporary service failure as appropriate. |

Do not return `200` with an error body.

## Rate limiting and abuse controls

Limits are policy-driven and segmented by risk:

- IP/device-oriented limits for public search and account discovery;
- account and IP limits for authentication/recovery;
- customer limits for reservation attempts and active reservations;
- user/store limits for uploads and imports;
- strict, monitored controls for administrative endpoints.

The response includes `Retry-After` when meaningful. Redis-backed limiting must define behavior during Redis outage: security-sensitive limits fail safe or use a bounded local fallback; low-risk public reads may fail open with alerting.

Initial policy values are configuration, not contractual guarantees: login and recovery are limited per account/IP, reservation creation per customer/IP/store, upload intent and bytes per user/store, and public search per IP/session. Load tests and pilot abuse data set numerical thresholds before production; client contracts rely on `429`, `Retry-After`, and standard rate-limit headers rather than a fixed quota.

## Caching

- Authenticated responses are `private, no-store` by default.
- Public resources may use ETag and bounded `Cache-Control` after their invalidation/staleness impact is reviewed.
- Search results use short or no intermediary caching until query behavior is measured.
- Reservation and exact availability mutation responses are not shared-cacheable.
- Cache keys vary by every representation-affecting input, locale, and authorization scope.

## Upload API

The upload flow is:

1. authenticated client requests an upload intent with purpose and safe metadata;
2. backend validates permission, file class, size, and owner scope;
3. backend creates a pending upload record and short-lived signed R2 authorization;
4. client uploads directly;
5. client requests finalization;
6. backend verifies object metadata and marks it usable;
7. owning feature associates the verified upload.

Signed authorization is single-object, short-lived, method-restricted, content-constrained where supported, and never grants bucket listing.

## Asynchronous operation contracts

When returning `202`, expose a status resource containing:

- opaque operation ID;
- state (`queued`, `running`, `succeeded`, `failed`);
- safe progress counts where meaningful;
- structured failure summary;
- creation/update timestamps;
- link to result or report.

Clients poll with bounded backoff unless a future approved push mechanism exists.

## OpenAPI governance

- The reviewed OpenAPI file is linted and breaking-change checked before implementation.
- FastAPI-generated OpenAPI is built in CI as an implementation-conformance artifact.
- Operation IDs are stable and intentionally named.
- Every endpoint documents auth, request, responses, errors, examples, and deprecation.
- CI detects breaking changes against the main branch.
- Generated TypeScript clients/types are reproducible and never hand-edited.
- Sensitive/admin schemas are not accidentally included in public examples.

Contract releases use Semantic Versioning in the API changelog even while the deployed path remains `/api/v1`. Additive releases increment minor, compatible fixes increment patch, and breaking changes require a major path/version and explicit migration plan.

## Minimum endpoint capability map

Exact paths are finalized during API design, but the v1 contract must cover:

| Audience | Capabilities |
|---|---|
| Public | Search, public product detail, public store detail, taxonomy/reference reads. |
| Customer | Account/session control, reservation create/list/detail/cancel, notifications. |
| Store | Store profile, memberships/invitations, products/variants/publication, inventory/movements/imports, reservation processing, uploads, store aggregates. |
| Admin | Store review/status, moderation, support reads, audit queries, approved policies, platform aggregates and operational health. |

CRUD endpoints are not required merely because a table exists. APIs expose user/business capabilities.
