# Reviewer walkthrough

## Product story

An alert identifies a symptom. A responder still needs service ownership, urgency, evidence, context, and a shared response record. Stratum joins that information without pretending that an AI-generated paragraph proves a root cause.

The seeded workspace has six services, three active incidents, a two-week history, and a viewer account. Everything in the initial dataset is synthetic. New operations use the real database and worker.

## Live path

1. Sign in and explain why “services without incidents” is not the same as measured uptime. Open the service catalog to see objectives and owners.
2. Send a Checkout API signal with `checkout.demo-review` as its fingerprint and a deployment reference.
3. Show the instant receipt followed by asynchronously populated triage. Explain why the API does not call the model during ingestion.
4. Expand a proposed investigation. Record an approval and its rationale. Point out that a manual investigation decision is separate from running an infrastructure command.
5. Acknowledge, mitigate, and resolve. The last step requires a meaningful resolution note.
6. Repeat the fingerprint while an incident is active to show correlation. After resolution, the same fingerprint can create a new incident.
7. Sign in as the viewer. The server also rejects write requests, regardless of whether the UI hides the buttons.

## Demonstrate the failure cases

Run the Postgres tests with `pytest -k 'concurrent or lease or stale or tenant' -v`.

| Reviewer question | Evidence to show |
| --- | --- |
| What happens when a webhook is delivered eight times at once? | Concurrent receipt test; receipt unique constraint; one committed job |
| Can two different alerts lose a signal count? | Concurrent distinct-key correlation test; row lock and active partial index |
| What happens if a worker is killed? | Lease reclaim test; attempts, lease token, fenced publication |
| Can a stale worker overwrite newer evidence? | Version check and fresh-job test |
| Can a forged workspace field cross tenants? | Strict request schema and tenant isolation tests |
| How does the system behave when Redis disappears? | Production fail-closed limiter test and database-backed SSE replay |
| Why add a model at all? | Optional readability improvement; core evidence and decisions work without it |
| What would you change at ten million incidents? | SQL rollups, retention/partitioning, event fanout, queue isolation, and measured load tests |

## Honest portfolio positioning

Suggested project description:

> Built a tenant-isolated incident command center using async FastAPI, Next.js, PostgreSQL, and Redis. Implemented transactional ingestion, idempotent correlation, leased background processing with fencing, optimistic incident updates, and authenticated live event replay. Added generated API contracts, integration tests, browser accessibility checks, container delivery, and operational runbooks.

Only attach measured test/benchmark results from your own run. Do not describe demo data as customers, uptime, revenue impact, or production traffic. A strong interview discussion covers both the invariants and the limits.

## Next real contributions

Choose one feature after using the application, rather than adding unrelated technologies:

- An authenticated Alertmanager adapter with signature/replay protection and a contract test.
- OpenID Connect with managed identity, workspace membership administration, and per-session revocation.
- SQL-based analytics rollups validated against the current reference implementation.
- A load test with queue-age and lease-expiry instrumentation, followed by a measured bottleneck fix.
- Immutable audit export with explicit retention guarantees.

Those changes provide an authentic development history. This initial repository is a foundation; it cannot itself manufacture an active contribution history or a hiring outcome.
