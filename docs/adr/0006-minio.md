# ADR 0006: MinIO for Local Object-Storage Development

- Date: 2026-07-30
- Status: Accepted

## Context

The approved production object store is Cloudflare R2. Developers and CI need an S3-compatible environment that works locally without production credentials or network dependency.

## Decision

Use MinIO only as the local and test S3-compatible object-storage implementation. Use Cloudflare R2 in production.

Both are accessed behind the Uploads module's storage abstraction and configured through environment settings. Buckets are private by default, upload validation occurs before persistence, and externally accessible objects use controlled signed or proxied access according to the security design.

## Alternatives considered

- Cloudflare R2 for every environment: rejected because it requires external connectivity, credentials, and ongoing usage for local development.
- Local filesystem storage: rejected because its semantics differ substantially from object storage.
- LocalStack: viable but broader and heavier than the single S3-compatible capability required.

## Consequences

- Local development is reproducible and does not require cloud secrets.
- S3 compatibility is not perfect provider equivalence; staging must verify R2-specific behavior, limits, CORS, signing, and lifecycle policies.
- Production code must not depend on MinIO administration APIs.
- Object metadata in PostgreSQL remains distinct from binary object storage.
