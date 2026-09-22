# Release verification

Recorded for Stratum v1.0.0 on **20 September 2026**. These are observed local results, not a claim of an already completed GitHub Actions run or a production deployment.

## Executed successfully

| Check | Result | Environment / scope |
| --- | --- | --- |
| Backend regression suite | **46 passed, 1 explicitly skipped** | Python 3.13.7, Windows 11, real PostgreSQL 18.4 |
| Combined statement/branch coverage | **90.47%** | Runtime modules; seed, bootstrap, and schema-export CLI modules excluded by documented coverage config |
| Backend formatting and lint | Passed | Ruff; application, tests, migrations |
| PostgreSQL schema migrations | Passed | Initial upgrade and `alembic check`; no schema drift |
| TypeScript validation | Passed | Generated OpenAPI response types and strict TypeScript |
| Production frontend build | Passed | Next.js 16.3.5, React 19.3.0, Node.js 22.20.0 |
| Browser regression suite | **5 passed** | Real Chromium, standalone Next.js server, FastAPI, independent worker, PostgreSQL |
| Automated accessibility | No reported WCAG 2 A/AA or 2.1 AA violations in tested views | Overview, incident drawer, and mobile overview using axe |
| Mobile overflow | Passed | 390 px viewport; document width also 390 px |
| Dependency audit | No known vulnerabilities reported in the recorded scans | npm audit and pip-audit; see audit dates below |

The browser suite covers signal ingestion through triage, approval, acknowledgement, mitigation and resolution; service registration and duplicate-slug feedback; viewer restrictions and HttpOnly sessions; sign-out; keyboard dialog dismissal; responsive layout; cross-origin rejection; and rejection of private proxy paths.

The backend suite includes concurrent duplicate delivery, distinct-key correlation without lost signals, simultaneous operator updates, tenant isolation, token validation, role changes, expired worker leases, in-flight lease expiry, crash retry exhaustion, stale evidence rejection, SSE cursor replay, model action-injection rejection, and fail-closed rate limiting.

The final browser run verified the fix for an in-flight response clearing a newer unsaved note. A completed mutation now clears only the exact text submitted, preserving a subsequent draft.

## Infrastructure checks not executed locally

- **The one skipped backend test** requires a real Redis server for the Lua rate-limit script. Other tests use a Redis test double and explicitly exercise outage behavior.
- **Docker image builds and the full Docker Compose stack** were not run on this machine because no Docker runtime was available. The application itself was built and exercised against real PostgreSQL outside containers.
- **GitHub Actions** has not run for this project yet because the source has not been published to a GitHub repository. The included workflow runs real Redis and PostgreSQL tests and the container/browser stack on the first push.
- The optional model gateway was tested through controlled responses and failure injection, not a live model vendor. No model-quality score is claimed.
- No external deployment, failover test, penetration test, continuous telemetry integration, or capacity certification is claimed.

These limits mean **ready to publish as a tested portfolio release**, not certified for unattended production operation. Wait for the first GitHub Actions run before claiming the container pipeline passes.

## Dependency audit dates

Both the initial scans on 17 September 2026 and the refreshed release scans on 20 September 2026 reported no known vulnerabilities. The release used `npm audit --audit-level=high` and `pip-audit -r requirements.lock --disable-pip`. An audit is a point-in-time database lookup and does not establish that a dependency is vulnerability-free.

## Small local performance probe

[`benchmark-local.json`](benchmark-local.json) records a 17 September authenticated incident-list probe against local PostgreSQL:

- 200 requests, concurrency 10, zero failed requests.
- Median 223.22 ms; p95 436.59 ms.
- 39.86 requests/second over a 5.018-second sample.

The probe used a small development dataset on a shared Windows workstation, directly against FastAPI; Redis was unavailable and development fallbacks were enabled. It does not include BFF/network deployment overhead, ingestion, worker saturation, large-tenant aggregation, or long-duration behavior. Do not turn these numbers into a production capacity or SLO claim.

Reproduce with `scripts/benchmark.py` and a valid `STRATUM_TOKEN`; it records platform, sample size, concurrency, errors, and latency percentiles without writing the token. Rerun against your actual deployment before optimizing or making performance claims.

## Reproduce the release checks

Follow the README's Verify section. Use Postgres for concurrency tests and a dedicated Redis test database to run the previously skipped Lua-script check. The GitHub Actions workflow stores backend test reports and browser/container diagnostics for a remotely reproducible result.
