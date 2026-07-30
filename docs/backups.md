# Backup and Restore

## General policy

Backups are encrypted, access-controlled, monitored, retention-governed, and separate from ordinary runtime credentials. Backup operators cannot make routine application changes. Restore exercises use isolated nonproduction networks and synthetic or appropriately controlled data.

## PostgreSQL

- Use managed automated backups plus point-in-time recovery with WAL retention sufficient for RPO at most 15 minutes.
- Retain daily/weekly/monthly copies according to the approved legal and operational schedule.
- Alert on backup, WAL archive, storage, integrity, encryption, and retention failures.
- Restore quarterly to an isolated instance; never overwrite the source database as a test.
- Verify PostgreSQL version/extensions, roles, schema heads, constraints, counts, timestamps, and application-level behavior.
- Document recovery-point selection and the expand/migrate/contract compatibility of the application image.

## PostgreSQL restore outline

1. Declare an exercise/incident and select the recovery point.
2. Provision an isolated encrypted target with no public access.
3. Restore the provider backup/PITR stream.
4. create least-privilege runtime and migration roles through controlled automation;
5. validate server encoding/timezone, migration heads, constraints, row counts, and checksums/samples;
6. deploy a compatible application release and run smoke/integrity checks;
7. destroy exercise data according to policy or proceed through disaster cutover approval.

Provider-specific commands belong in the selected-provider runbook and must not embed credentials.

## MinIO and Cloudflare R2

- Production R2 originals/derivatives require a reviewed versioning, replication/export, lifecycle, and privacy-deletion policy based on R2's verified capabilities.
- Configuration, bucket policy, CORS, key namespaces, lifecycle rules, and media transformation definitions are version-controlled/exported.
- Local MinIO volumes are disposable developer data, not a production backup.
- Recovery validates object count, size, hashes for samples/manifest, metadata, private access, and references from PostgreSQL.
- Deleted content must not be restored past an approved privacy/legal deletion boundary.

## Configuration and secrets

- Git protects non-secret application, OpenTofu, monitoring, RabbitMQ topology, Meilisearch settings, and policy configuration.
- OpenTofu state uses encrypted, locked, versioned remote storage with independent access/recovery.
- Secret-manager configuration, key metadata, access policy, and emergency rotation procedures are recoverable; secret values are never copied into Git backups.
- Container images, provenance, SBOMs, and scan results are retained by immutable digest for the release/rollback window.

## RabbitMQ

- Define users, virtual hosts, exchanges, durable queues, bindings, dead-letter routing, policies, and permissions as controlled configuration.
- Managed RabbitMQ node/config backups supplement but do not replace code-defined topology.
- PostgreSQL outbox/reconciliation is the future authoritative recovery path for business effects; queue contents are not the only record.
- A restore exercise recreates topology, connects least-privilege publishers/consumers, verifies confirms/acknowledgements, and safely replays pending outbox work.

## Redis and Meilisearch

Redis is ephemeral and does not require authoritative backup. Recreate it empty and accept cache misses/session behavior defined in Phase 2.

Meilisearch settings/synonyms/ranking/index schema are version-controlled. Search documents are rebuilt from PostgreSQL. Any provider snapshot is an acceleration only and must pass eligibility/forbidden-field reconciliation before use.
