# Security model

## Implemented boundaries

- Signed, expiring HS256 sessions verify issuer, audience, subject, tenant, issued time, and expiry. Every request reloads the current user record and role.
- Passwords use salted scrypt; comparisons are constant-time. Password verification runs off the event loop.
- Browser credentials stay in HttpOnly, SameSite=Strict cookies. The BFF enforces exact Origin checks for mutations, proxies only approved paths, and never exposes the bearer token in its login response.
- Production requires secure deployment configuration. HTTPS and `COOKIE_SECURE=true` are deployment requirements; local HTTP intentionally uses a non-Secure cookie.
- Strict request models reject extra fields, including attempted tenant spoofing. Resource lookups, writes, event replay, and job operations are tenant scoped.
- Operator actions are authorized on the API, not merely hidden in the UI. Admin-only registration and dead-job retry are independently tested.
- Distributed rate limits fail closed in production. The BFF limits body size while reading, and the backend rejects declared bodies larger than 64 KB. Apply a hard ingress body limit for direct/chunked backend traffic as well.
- Curated action IDs are allowlisted. Model summaries cannot create or execute infrastructure actions. React renders incident and model text without raw HTML.
- Audit, incident, receipt, and job state are committed transactionally. Optimistic versions protect against stale decisions.
- Database and broker ports are private in Compose. API and worker images run without root. Secrets and local state are excluded from Git and Docker build contexts.

## Threats explicitly considered

Cross-tenant direct object reference, stale authorization claims, replayed signals, idempotency-key collision, lost updates, duplicate worker execution, stale worker publication, model-injected actions, CSRF, browser token exposure, high-cardinality metrics, and accidental credential logging.

## Remaining deployment work

This is a portfolio release, not a security certification. It has no OIDC/SSO, MFA, password recovery, user-management UI, per-device refresh/revocation store, or immutable external audit sink. Sign-out removes the browser cookie; a copied bearer token remains valid until expiry unless the user record is removed or the signing secret is rotated. Sessions default to one hour. An already-open SSE stream can continue for up to 55 seconds before membership is rechecked.

Isolation is enforced in application code and tested against Postgres. Database row-level security is not configured. Database operators can change audit records. Separate database roles and immutable external exports are appropriate for regulated environments.

The current CSP allows inline scripts/styles because of the Next.js rendering setup. It blocks framing and restricts resource origins, but a nonce-based strict CSP would be a useful hardening step. Proxy body/path checks, React escaping, and HttpOnly cookies are independent controls, not substitutes for fixing XSS vulnerabilities.

Rate limiting is fixed-window and account-scoped for login, tenant-scoped for ingestion. Trusted edge/IP throttling is required for distributed abuse. Production secret rotation, encrypted transport, dependency patching, backups, and provider data-handling approval remain the operator's responsibility.

## Report a vulnerability

When you publish your own repository, enable GitHub private vulnerability reporting. Use that private channel for a reproducible issue and avoid posting credentials or exploitable customer details in public issues. No nonexistent security email address is supplied by this template.
