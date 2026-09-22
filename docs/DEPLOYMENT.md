# Deployment and operations

## Local demo topology

`compose.yaml` starts PostgreSQL 18, Redis 8, a migration job, FastAPI, an independent worker, and the Next.js standalone server. The optional `demo` profile seeds sample data. The optional `observability` profile starts Prometheus.

Postgres 18 mounts its named volume at `/var/lib/postgresql`, matching the [official image layout](https://docs.docker.com/guides/postgresql/immediate-setup-and-data-persistence/). Do not attach a data volume from another Postgres major version without a proper migration.

Application containers run without root, drop Linux capabilities, use a read-only root filesystem, and have a temporary `/tmp`. Source-only multi-stage builds exclude local databases, secrets, test caches, and node_modules. Python packages are hash-locked; npm uses `npm ci`.

Docker base images use maintained version tags. For a controlled deployment, resolve them to approved digests and establish an update policy. No image signatures, SBOM publication, or container vulnerability scan results are claimed by this repository.

## Deploy with your infrastructure

1. Provision a managed Postgres database and a private Redis instance with encryption, backup, and access controls appropriate to your environment.
2. Set `ENVIRONMENT=production`, a unique `JWT_SECRET` of at least 32 characters, `DATABASE_URL`, and `REDIS_URL`. Production rejects SQLite and insecure signing defaults. Use your secret manager, not a committed file.
3. Run `alembic upgrade head` once as a release step before the API and worker. The Compose migration service demonstrates ordering, but a real release should have one migration owner.
4. Create the first administrator explicitly:

   ```bash
   python -m app.bootstrap --email you@example.com --name "Your Name" --workspace "Your Organization"
   ```

   It prompts for a password. For controlled automation, inject `BOOTSTRAP_PASSWORD` from a secret manager and unset it after the bootstrap job. There is no default production account or public signup endpoint.

5. Build the frontend with `NEXT_PUBLIC_DEMO_MODE=false`. Set runtime `API_BASE_URL` to the private backend address, `APP_ORIGIN` to the exact external HTTPS origin, and `COOKIE_SECURE=true`.
6. Place the frontend behind your TLS ingress. API, metrics, Redis, and Postgres must remain private. Preserve SSE streaming and disable proxy buffering for `/api/v1/stream`; use an idle timeout longer than 65 seconds.
7. Configure ingress request-size limits, IP-based abuse controls, certificate renewal, backup monitoring, log retention, and operational alert delivery.
8. Separate the migration role from the runtime database role. Give the API/worker only needed DML rights. Application code does not expose audit deletion, but the demo database user is not an immutable-audit security boundary.

The shipped Compose file binds the web port to localhost. For remote use, put your ingress on the appropriate network or deliberately adapt the binding. Do not simply make all service ports public.

## Health and metrics

| Endpoint | Purpose |
| --- | --- |
| `/health/live` | Process can answer a request |
| `/health/ready` | Both database and Redis are reachable |
| `/metrics` | Internal Prometheus request counts and duration histograms |

The metrics labels contain method, route template, and status, not user IDs, raw URLs, tokens, or incident IDs. Structured API logs include request IDs and durations. Worker logs include job IDs and tenant IDs. Model exception bodies are not stored on jobs.

Prometheus alert examples cover unavailability, elevated 5xx rate, and API latency. They demonstrate rules only; configure Alertmanager or your alert delivery service separately. There are no claimed production SLOs for Stratum itself.

## Scale workers

```bash
docker compose up -d --scale worker=3
```

Postgres `SKIP LOCKED` prevents two workers from claiming the same live job. Never scale the SQLite development worker. Each worker currently processes one job at a time, which bounds downstream concurrency. Model calls have a 15-second timeout inside a 45-second lease.

## Runbook: triage is delayed

1. Inspect **Job operations**. Distinguish pending, running, and dead jobs.
2. Inspect `docker compose logs worker` and database availability. The worker logs poll failures and retries after a bounded pause.
3. If a worker crashed while running, allow its lease to expire. Another worker will reclaim it. Do not manually duplicate jobs unless you understand their current lease.
4. For dead jobs, inspect the stored error class. Fix the cause, then use **Retry job** as an administrator. Retries are audited.
5. If pending work grows persistently, inspect database load and gateway latency before adding workers. A larger worker pool can overload a shared model gateway or the database.

## Runbook: Redis is unavailable

New logins and signal ingestion requiring distributed rate limits fail closed in production. Existing authenticated reads and database workers continue where possible. SSE falls back to database polling. Readiness fails, allowing an orchestrator to remove the API from service. Restore Redis, verify readiness, and confirm receipt replays before asking producers to resend signals.

Redis persistence does not provide incident durability; Postgres does. Redis uses `noeviction` so pressure fails visibly instead of silently evicting security rate counters. Size and monitor Redis capacity.

## Runbook: migration or release failure

Back up before schema changes. Apply migrations to a restored staging copy and inspect `alembic check`. The initial migration has a downgrade for development, but downgrading it destroys the application's tables; do not use it as a production rollback plan. Prefer forward fixes and application releases compatible with both sides of a rolling schema change.

Keep the previous application image digest, database backups, and deployment configuration. Validate restore into a separate database and compare tenant/service/incident counts before a cutover. This project does not configure point-in-time recovery or test your managed backup service.

## Backup example

On a Unix-like host, stream a dump to a file owned by your backup process:

```bash
docker compose exec -T postgres pg_dump -U stratum -d stratum -Fc > stratum-backup.dump
```

Store backups encrypted and outside the container host; test restoring to a separate database. Windows PowerShell versions differ in binary redirection behavior, so use a backup tool or a container-mounted destination instead of assuming that example preserves binary bytes on every shell.

## Retention and capacity

No automatic pruning currently removes receipts, events, incidents, or jobs. Receipt replay is durable for as long as its receipt exists. Define a published retention window before adding cleanup. Plan incident-history rollups, partitioning, database connection limits, and SSE fanout measurements before claiming large-scale capacity.
