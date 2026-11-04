# Agent instructions

This repository is an interview assessment: an internal, multi-tenant certificate admin console.

## Stack

- Backend: Python, FastAPI, PostgreSQL
- Frontend: Vue 3, built by Vite and served by FastAPI
- Identify the actor with the `X-Actor-Token` header. There is no login flow.

## Leave these alone

- Do not draft, outline, translate, rephrase, proofread, or improve `written-answers.md`. That section is written by the candidate alone.
- Do not commit or push unless the user explicitly asks.
- Do not add the 100,000-row generator to the default startup path.

## Behavior that must stay true

- A caller only sees and changes their own tenant. A cross-tenant detail, bulk issue, or revoke returns 404 and writes no certificate and no audit event.
- The same idempotency key and the same payload are one bulk-issue operation, including when the calls overlap. The same key with a different payload returns 409 and does not overwrite the stored result.
- A learner has at most one certificate per course in a tenant. Each certificate has at most one `issued` audit and one `revoked` audit.
- Repeating a revoke does not write another audit event.
- Store issuance instants in UTC. Sort the list by the tenant-local calendar date, then by certificate id ascending, so equal dates stay in a stable order. Show the tenant-local time as `YYYY-MM-DD HH:MM`.
- East uses `Australia/Sydney`. West uses `Australia/Perth`. `2026-01-10T13:30:00Z` is `2026-01-11 00:30` in East and `2026-01-10 21:30` in West.
- Eligible learners are enrollments with status `completed` and no certificate yet. Incomplete enrollments are `skipped / not_completed`. Existing certificates are `skipped / already_certified`.
- CSV export uses the same tenant filter, search, and sort as the list. Stream it from a server-side cursor on one thread. Do not load every matching row into a list first.
- `scripts/generate_volume.py` may add 100,000 East rows. `python start.py` must not.
