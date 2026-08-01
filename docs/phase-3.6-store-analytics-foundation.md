# Phase 3.6 Store Analytics Foundation

## Scope

Phase 3.6 adds Store-owned operational analytics inside the existing Store
bounded context. It records immutable metric facts, maintains transactional
UTC daily aggregates, and exposes owner- and administrator-scoped reads.

This is not business intelligence, financial reporting, customer analytics,
search analytics, product analytics, recommendations, or machine learning. It
does not add workers, scheduled jobs, frontend behavior, Redis state,
RabbitMQ messages, PostHog capture, or a second analytics datastore.

## Architecture

```text
Existing Store use case
    -> typed Store event
        -> StoreAnalyticsEventPublisher
            -> existing safe Store logger
            -> StoreAnalyticsService
                -> immutable metric-event insert
                -> authoritative Store snapshot lookup when required
                -> daily aggregate upsert
                -> safe analytics events and Prometheus metrics
                    -> same request-scoped PostgreSQL transaction

Store Analytics API
    -> authorization permission decision
    -> Store ownership or explicit administrator scope
    -> StoreAnalyticsService
    -> StoreAnalyticsRepository
    -> PostgreSQL
```

Repositories flush but never commit. Store request dependencies control
commit and rollback, so the originating Store mutation, metric fact, and daily
aggregate succeed or fail together. PostgreSQL is authoritative.

## Persistence

Alembic revision `0f01b7088f73` follows Store Operating Hours revision
`077498dfaa91` and creates exactly two tables.

### `store_daily_metrics`

One row exists per Store and UTC calendar date.

| Column | Meaning |
|---|---|
| `id` | Application-generated UUIDv7 primary key |
| `store_id` | Required Store reference with restrictive deletion |
| `metric_date` | UTC aggregate date |
| `profile_views` | Recorded Store profile views |
| `gallery_views` | Recorded gallery views |
| `media_uploads` | Completed logo, banner, and gallery uploads |
| `staff_invitations` | Created Store invitations |
| `staff_acceptances` | Accepted Store invitations |
| `verification_submissions` | Store verification submissions |
| `verification_approvals` | Store verification approvals |
| `verification_rejections` | Store verification rejections |
| `storage_bytes` | Snapshot of active, non-deleted media bytes |
| `active_members` | Snapshot of active Store memberships |
| `created_at`, `updated_at` | Timezone-aware database timestamps |
| `version` | Positive monotonic aggregate version |

`(store_id, metric_date)` is unique. Database checks prevent negative
counters, storage, membership snapshots, and versions. Indexes support Store,
date, and Store/date queries.

### `store_metric_events`

| Column | Meaning |
|---|---|
| `id` | Source event UUIDv7 and idempotency key |
| `store_id` | Required Store reference |
| `event_type` | Typed operational metric |
| `occurred_at` | Authoritative timezone-aware occurrence timestamp |
| `metadata` | Bounded JSONB containing only approved non-personal context |
| `created_at` | Database insertion timestamp |

Metric events are append-only. No repository update or deletion operation
exists. The source Store event ID is reused as the metric-event primary key.
Replaying an already-recorded event therefore performs `ON CONFLICT DO
NOTHING` and cannot increment a daily aggregate twice.

Metadata is limited to 16 fields and 2 KiB. Keys associated with email,
tokens, passwords, secrets, IP addresses, user agents, authorization, or
cookies are rejected. Existing Store integrations record only the safe source
event name.

## Event integration

The transactional publisher recognizes:

| Existing Store event | Metric effect |
|---|---|
| `StoreVerificationSubmitted` | Increment verification submissions |
| `StoreVerified` | Increment verification approvals |
| `StoreVerificationRejected` | Increment verification rejections |
| `StoreMemberInvited` | Increment invitations and refresh active members |
| `StoreMemberAccepted` | Increment acceptances and refresh active members |
| `StoreLogoUploaded` | Increment media uploads and refresh active bytes |
| `StoreBannerUploaded` | Increment media uploads and refresh active bytes |
| `StoreGalleryUploaded` | Increment media uploads and refresh active bytes |
| `StoreMediaDeleted` | Refresh active bytes without decrementing upload history |

Membership decline, suspension, reactivation, and removal events refresh the
current active-member snapshot without creating an unapproved counter.

Event payloads are not trusted for storage or membership totals. The analytics
source adapter recalculates these values from authoritative `store_media` and
`store_memberships` rows after the originating mutation has flushed.

Profile and gallery view metric types are available through the application
service for future approved Store-detail consumers. Phase 3.6 does not add a
public recording endpoint or fabricate view events.

## Domain model

- `StoreAnalytics`: summary plus a bounded daily page;
- `DailyMetrics`: one immutable application representation of a daily row;
- `MetricEvent`: one append-only operational fact;
- `MetricType`: allowlisted metric registry;
- `AnalyticsSummary`: period counter totals and latest snapshots;
- `AnalyticsPeriod`: inclusive UTC date range.

Periods default to the latest 30 UTC dates and cannot exceed 367 days.

## API

| Endpoint | Result |
|---|---|
| `GET /api/v1/stores/{store_id}/analytics` | Summary and paginated daily metrics |
| `GET /api/v1/stores/{store_id}/analytics/summary` | Period summary |
| `GET /api/v1/stores/{store_id}/analytics/daily` | Paginated newest-first daily rows |
| `GET /api/v1/stores/{store_id}/analytics/storage` | Current authoritative active-media bytes |

The aggregate, summary, and daily endpoints accept inclusive `date_from` and
`date_to` filters. Aggregate and daily responses accept bounded `offset` and
`limit` pagination using the established response metadata.

Routes declare `store:view OR admin:access`. The application layer then
enforces ownership unless authorization explicitly confirms `admin:access`.
There are no role-name comparisons. Missing and cross-Store owner requests
return the same `404`.

## Analytics events

- `StoreMetricRecorded`;
- `StoreAnalyticsUpdated`;
- `DailyMetricsCreated`.

Payloads contain only Store ID, metric type, UTC metric date, value, and the
shared safe event timestamp. They contain no personal or authentication data.

## Metrics

The label-free Prometheus instruments are:

- `fashion_network_store_metric_events_total`;
- `fashion_network_store_daily_updates_total`;
- `fashion_network_store_storage_bytes`;
- `fashion_network_store_profile_views_total`.

No Store, event, user, date, or other high-cardinality label is used.

## Operational semantics

- Counters are historical period totals.
- Storage bytes and active members are point-in-time snapshots on daily rows.
- Summary responses use the latest snapshot in the selected period.
- The storage endpoint recalculates current active media directly from
  PostgreSQL.
- Archived and soft-deleted media are excluded from active storage.
- Metric events are immutable; aggregate rows use atomic upserts and monotonic
  versions.
- UTC dates are deliberate and stable. User-facing local-date reporting is a
  future separately reviewed concern.

## Phase 3.7 boundary

Phase 3.7 may implement only the next approved Store capability. It must not
turn this foundation into revenue, order, payment, customer, product, search,
marketing, or recommendation analytics. Future modules integrate through the
application recording contract and must not mutate daily aggregates or query
analytics ORM models directly.

