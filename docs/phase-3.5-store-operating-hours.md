# Phase 3.5 Store Operating Hours

## Scope

Phase 3.5 adds Store-owned weekly operating schedules, temporary overrides,
timezone-aware status calculation, and next-transition calculation inside the
existing Store bounded context.

It does not add reservations, delivery or pickup windows, inventory
availability, appointments, employee shifts, non-Store holiday calendars,
notifications, workers, schedulers, search indexing, frontend, or dashboard
behavior. Identity, authentication, authorization, Store profile,
verification, membership, and media remain backward compatible.

## Architecture

```text
Store Operating Hours API
    -> StoreOperatingHoursService
        -> StoreOperatingHoursValidationService
        -> StoreRepository (ownership boundary)
        -> StoreOperatingHoursRepository
        -> StoreOperatingHoursAuditService
            -> PostgreSQL transaction
            -> safe in-process events
            -> low-cardinality Prometheus metrics
```

The API dependency controls commit and rollback. Repositories call `flush()`
but never `commit()`. PostgreSQL is authoritative. Redis, RabbitMQ,
Meilisearch, and object storage are not used by this capability.

The domain types are:

- `StoreOperatingHours`: one persisted Store/day interval or closed/all-day
  rule;
- `OperatingInterval`: a local opening and closing wall-clock pair;
- `StoreSchedule`: the resolved interval set for a local weekday and priority;
- `OpenState`: `open` or `closed`;
- `BusinessStatus`: the computed status contract, current interval, resolved
  schedule, and next transitions.

## Persistence

Alembic revision `077498dfaa91` follows the Phase 3.4 Store Media head
`2eb2bce458d5`.

| Column | Rule |
|---|---|
| `id` | Application-generated UUIDv7 primary key |
| `store_id` | Required Store reference with restrictive deletion |
| `day_of_week` | Integer `0` (Monday) through `6` (Sunday) |
| `timezone` | Required IANA timezone; defaults to `Asia/Kolkata` |
| `opening_time`, `closing_time` | Local wall-clock times for a bounded interval |
| `is_closed` | Closed-day or temporary-closure rule |
| `is_24_hours` | All-day open rule |
| `effective_from`, `effective_until` | Optional paired UTC instants for a temporary rule |
| `priority` | Non-negative resolution priority |
| `notes` | Optional normalized operational note, at most 500 characters |
| `created_at`, `updated_at` | Database-populated timezone-aware timestamps |
| `deleted_at` | Soft-deletion timestamp |
| `version` | Positive optimistic-lock version |

The IANA timezone is persisted because a Store status cannot be reproduced
from address text or a request-local timezone. All non-expired, non-deleted
rules for one Store must use one timezone. `Asia/Kolkata` is the safe initial
default for the Manipur launch region.

The schema enforces valid days, non-negative priorities, positive versions,
paired and ordered effective periods, notes length, and exactly one operating
mode:

- closed, with no opening or closing time;
- open 24 hours, with no opening or closing time; or
- a bounded interval where opening is earlier than closing.

Explicit partial indexes cover Store/day/priority resolution, effective-range
lookups, and active Store listings.

## Interval and priority rules

Each row is one interval rule. This is the smallest persistence unit required
by the approved table shape and optimistic endpoint.

Multiple non-overlapping intervals may use the same Store, weekday, effective
period, and priority. This represents split hours such as `09:00–12:00` and
`13:00–17:00`. At equal priority, overlapping wall-clock intervals with
overlapping effective periods are rejected.

Closed and 24-hour rules occupy the full local day, so they conflict with any
equal-priority rule whose effective period overlaps. The repository takes a
transaction-scoped PostgreSQL advisory lock for Store/day/priority before
conflict validation and insertion or update. This closes the empty-result race
without introducing an extension or a second persistence table.

Resolution follows these steps:

1. Convert the authoritative instant into the Store IANA timezone.
2. Select non-deleted rules for the local weekday.
3. Ignore expired or not-yet-effective temporary rules.
4. If any temporary rules are effective, ignore recurring rules.
5. Select every non-overlapping interval at the highest remaining priority.
6. Resolve closed, 24-hour, or bounded interval state.

Temporary rules therefore override recurring schedules. Higher priorities
override lower priorities. Expired rules remain visible in management history
but never affect current status.

## Status and transitions

`GET /status` returns:

- Store ID and IANA timezone;
- `open` or `closed` and an `open_now` boolean;
- whether the active schedule is 24 hours;
- the current interval, if any;
- today's resolved schedule;
- the next opening and next closing as UTC RFC 3339 timestamps;
- whether a temporary override won resolution.

Transition discovery evaluates schedule boundaries for the next 14 local
days, plus temporary effective boundaries. It compares the resolved state
immediately before and after each boundary. This handles split intervals,
temporary closures, activation, expiry, and priority changes without polling
or a background worker.

Overnight intervals are intentionally not represented as `opening_time >
closing_time`. A Store expresses an overnight period as two rules on adjacent
days, preserving the database invariant and unambiguous weekday ownership.

## API

| Method and path | Permission | Result |
|---|---|---|
| `POST /api/v1/stores/{store_id}/hours` | `store:update` | Create one recurring or temporary rule |
| `GET /api/v1/stores/{store_id}/hours` | `store:view` | List non-deleted rule history |
| `GET /api/v1/stores/{store_id}/hours/today` | `store:view` | Resolve today's active schedule |
| `PATCH /api/v1/stores/{store_id}/hours/{schedule_id}` | `store:update` | Optimistically update one rule |
| `DELETE /api/v1/stores/{store_id}/hours/{schedule_id}` | `store:update` | Soft-delete one rule |
| `GET /api/v1/stores/{store_id}/status` | `store:view` | Calculate current business status |

All routes require the frozen bearer authentication dependency and typed
permission checks. No route compares role names. The application service
enforces Store ownership, and cross-Store access returns the same `404` as a
missing resource. Errors use the common RFC 9457 representation.

## Events

The Store event publisher accepts:

- `StoreHoursCreated`;
- `StoreHoursUpdated`;
- `StoreHoursDeleted`;
- `StoreOpened`;
- `StoreClosed` (`store.closed`, defined in the operating-hours event package);
- `StoreScheduleActivated`;
- `StoreScheduleExpired`.

Every payload contains only Store ID, schedule ID, timestamp, and status,
alongside the shared event envelope. It excludes notes, address data,
credentials, tokens, user identifiers, and request metadata.

Open/closed events describe a computed status observation; they are not
durable edge-trigger notifications. A future notification capability must
introduce explicit transition persistence or reconciliation rather than treat
repeated status queries as a notification stream.

## Metrics

Phase 3.5 adds four label-free instruments:

- `fashion_network_store_hours_updates_total`;
- `fashion_network_store_hours_queries_total`;
- `fashion_network_store_open_total`;
- `fashion_network_store_closed_total`.

No Store, schedule, user, timezone, or status label is attached.

## Verification

Tests cover:

- creation, UUIDv7, listing, repository transaction ownership, and soft delete;
- multiple intervals, overlap rejection, closed days, and 24-hour operation;
- temporary override, priority resolution, expiry, and timezone conversion;
- current interval, next opening, and next closing;
- optimistic stale updates and cross-Store concealment;
- database checks and explicit indexes;
- safe events and label-free metrics;
- permission dependencies and all six OpenAPI operations;
- downgrade, re-upgrade, and Alembic metadata drift.

The Phase 3.5 gate runs Black, Ruff, strict MyPy, the complete Pytest suite,
Alembic upgrade/downgrade/re-upgrade/check, Docker Compose health checks,
OpenAPI validation, dependency validation, Git whitespace checks, and
TODO/FIXME audits.

## Phase 3.6 boundary

Phase 3.6 may add only the next separately approved Store capability. It must
not reinterpret operating hours as inventory availability, reservation
capacity, delivery or pickup windows, staff shifts, or scheduled
notifications. Future consumers call the Store application contract; they do
not query the operating-hours persistence adapter directly.
