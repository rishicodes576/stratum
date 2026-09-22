# Architecture and engineering decisions

## Scope

Stratum coordinates response to alert evidence. An upstream monitoring system computes observations; Stratum stores, correlates, prioritizes, and records human decisions. The same application serves multiple workspaces with server-enforced isolation.

The frontend uses the Next.js App Router and a same-origin backend-for-frontend. FastAPI owns authorization, domain invariants, and persistence. Workers run as separate processes against the same database. SQLAlchemy uses a separate async session for each request or job transaction, as required by its [async session concurrency model](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks).

## Invariants

1. An accepted new signal has an incident, a receipt, an audit event, and a durable job in the same committed transaction.
2. A receipt key belongs to one tenant and one canonical payload digest. Replays cannot enqueue extra jobs.
3. At most one unresolved incident exists for a tenant, service, and fingerprint.
4. Every user-facing query and mutation derives its tenant scope from a verified session and current user row.
5. Incident status advances only along permitted transitions and only at the caller's expected version.
6. A worker can publish only while its lease token and unexpired lease still match the stored job.
7. Model output cannot alter severity, create runbooks, or execute tools.
8. Redis notification loss cannot lose incident data or permanently hide audit events.

The API, worker, isolation, and concurrency tests make these claims executable. `tests/test_api.py`, `tests/test_worker.py`, and `tests/test_reliability.py` are the highest-value review entry points.

## Decision 1: PostgreSQL as the durable work queue

**Accepted:** use a jobs table as a transactional outbox/work queue, with `FOR UPDATE SKIP LOCKED` for competing worker claims.

An external broker would introduce a dual-write problem: an incident could commit without a corresponding job, or a job could reference an uncommitted incident. Here the job is committed with its incident. A worker claims in a short transaction, releases the transaction before model/network work, and commits the result in another short transaction.

This is **at-least-once processing with fenced publication**, not exactly-once external execution. A crash can repeat analysis. Model summaries should therefore be side-effect free; the optional gateway may receive repeated requests and incur repeated costs. Curated runbooks are manually executed outside this system.

The lease is 45 seconds. Model calls time out after 15 seconds; the remaining time covers scheduling and persistence. If analysis becomes longer-lived, add lease heartbeats or a durable workflow engine. A replacement worker receives a new token. An old worker cannot publish even if it eventually returns.

Failed jobs back off for 2, 4, and 8 seconds before the fourth attempt. Exhausted jobs become dead. Repeated process crashes also consume the attempt budget. Administrators can retry dead jobs, and the retry itself produces an audit event.

Tradeoff: queue polling and write traffic share the primary database with API work. Monitor load and queue age. At higher scale, move to a transactional outbox relay and broker or workflow service while preserving the ingestion transaction and idempotency semantics.

## Decision 2: explicit concurrency control

The partial unique index arbitrates the initial incident-creation race. Existing incidents are locked while signals are correlated. A failed uniqueness race rolls back and retries the entire ingestion transaction. A unique receipt prevents two concurrent requests with the same key from creating side effects twice.

Operator transitions use `UPDATE ... WHERE id = :id AND tenant_id = :tenant AND version = :expected`. A zero-row update returns 409. The browser refreshes the incident so the operator sees current state before deciding again.

Triage stores its input incident version. If evidence or lifecycle changes during analysis, the old result is discarded and a new job is enqueued. This trades extra computation for truthful context. Several distinct signals can enqueue several analyses for the same incident; this version does not coalesce queued jobs.

## Decision 3: Redis is an accelerator, not the source of truth

Redis runs atomic fixed-window rate counters using a Lua `INCR`/`EXPIRE` script. Production fails closed on rate-limit outages. Development may fall back to a local counter for a convenient portable demo.

Redis pub/sub only wakes SSE loops early. Each loop reads the ordered, tenant-scoped event table from the client's cursor. On disconnect, EventSource sends `Last-Event-ID`; a reconnect can replay committed events. Connections rotate after 55 seconds to revalidate the session and bound a revoked membership's stream lifetime. A two-second database poll and a 30-second UI refresh provide fallbacks.

The authentication transaction is rolled back before opening the stream, so an idle SSE client does not pin an authenticated query's database connection. Each replay batch acquires its own short-lived session.

## Decision 4: evidence evaluation before model summaries

For an availability SLO expressed as a percentage:

```text
burn(window) = error_rate_percentage(window) / (100 - slo_percentage)
SEV1: burn(5m) >= 14.4 AND burn(1h) >= 14.4
SEV2: burn(1h) >= 6 AND burn(6h) >= 6
SEV3: otherwise; investigation signal, not a paging recommendation
```

The approach is informed by Google's [multi-window burn-rate alerting](https://sre.google/workbook/alerting-on-slos/). Stratum's sustained rule deliberately uses its available 1h/6h inputs; it is not an exact implementation of every window in that reference. Thresholds are a transparent initial policy, not a universal operational truth.

The UI labels the input as active alert evidence. It does not infer a 30-day remaining budget or continuous availability from a few observations. A deployment reference is correlation context, not proof of causation.

An optional model gateway receives evidence strings and can return only a summary. The response schema rejects additional fields. The summary is labeled for independent verification. No model key is shipped to the browser. See [AI-GATEWAY.md](AI-GATEWAY.md).

## Decision 5: same-origin BFF and typed contracts

The browser holds an HttpOnly, SameSite=Strict session cookie. The BFF checks Origin on writes, rejects unknown proxy paths, bounds request bodies, applies timeouts, and forwards the bearer token only to the configured backend. Production deployments enable Secure cookies and HTTPS.

FastAPI defines request and response schemas. OpenAPI is exported into the frontend, and TypeScript declarations are generated from that contract. CI checks both semantic schema drift and generated type drift. Types are compile-time checks, not runtime validation of every network response; FastAPI validates emitted responses.

## Failure matrix

| Failure | Result | Recovery |
| --- | --- | --- |
| Duplicate delivery | Original receipt, no additional job | Client may safely retry with the same body and key |
| Same key, changed body | 409 | Use a new key for a genuinely new observation |
| Two responders update together | One versioned write wins | Other responder refreshes and reconsiders |
| API crash before commit | Transaction rolls back | Client retries |
| API crash after commit, before response | Work remains committed | Receipt replay returns the result |
| Worker dies after claim | Lease eventually expires | Another worker claims it |
| Old worker returns after reclaim | Fenced publication fails | Current lease owner determines the result |
| Evidence changes during analysis | Result is discarded | Fresh job evaluates current evidence |
| Redis outage | Production writes requiring limits fail closed; SSE polls DB | Restore Redis; committed work is intact |
| Model timeout or invalid output | Deterministic evidence remains available | UI marks model summary unavailable |
| Database outage | API readiness fails; worker backs off | Restore DB; no in-memory queue is lost |

## Scaling and security boundaries

Indexes support active fingerprint lookup, tenant incident history, event cursors, and job eligibility. Cursor pagination avoids growing offsets. The API uses one session per task. Prometheus labels use route templates rather than incident IDs to avoid unbounded cardinality.

Current overview aggregation reads the tenant's incident history in Python. Replace it with SQL aggregates/materialized daily rollups before large-volume use. Add retention/partitioning for events, receipts, and jobs; no automatic retention currently invalidates replay promises. Many SSE clients each poll independently; a high-fanout deployment should multiplex replay. Account login throttling exists; edge/IP limits and abuse controls belong at a trusted ingress.

Tenant isolation is application-enforced and tested, not PostgreSQL RLS. The audit API is append-only, but database administrators can modify records. The Compose database role is convenient for demos and migrations; a deployed system should separate migration and runtime roles and revoke unnecessary DDL rights. See [SECURITY.md](../SECURITY.md).
