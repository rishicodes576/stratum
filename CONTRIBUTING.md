# Contributing

Keep changes centered on a user problem and an explicit invariant. A new framework is not a substitute for measured improvement.

1. Create a branch and describe the trigger, current behavior, and intended result.
2. Add an Alembic migration for schema changes. Never silently use `create_all` in the deployed app.
3. Add tests for meaningful domain and failure behavior. Tenant-scoped operations need cross-tenant tests; concurrent operations need Postgres tests.
4. Export OpenAPI and regenerate frontend types when contracts change.
5. Run backend lint, formatting, tests, migration drift checks, frontend type/format checks, and the production build. Run browser tests for user-flow changes.
6. Update architecture or operations docs when guarantees, configuration, or recovery behavior changes.

Use separate SQLAlchemy sessions for concurrent tasks. Keep remote calls outside database transactions. Do not add model-generated commands to the action catalog. Do not claim benchmark, deployment, or security results that you did not execute.

The seeded accounts are for local development only. Do not include `.env`, database files, tokens, logs containing secrets, or node_modules in commits.

Dependency changes update both manifests and lockfiles. Python uses `uv.lock` plus hash-locked runtime/development exports; frontend uses `package-lock.json`. Regenerate the exports after a uv dependency update. CI intentionally fails on contract drift and significant dependency vulnerabilities.
