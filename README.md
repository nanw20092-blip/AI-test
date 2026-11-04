# Certificate Admin Console

Internal admin API for a multi-tenant training platform. Tenant admins list certificates, issue them in bulk, and revoke them. The Vue 3 interface, CSV export, and 100,000-row generator are not in this increment.

## Requirements

- Docker, so PostgreSQL can be started locally
- Python 3.12

## Start

From this directory:

```powershell
python start.py
```

That command creates a virtual environment, installs Python dependencies, starts PostgreSQL, loads the demo data when the database is empty, and serves the API at <http://127.0.0.1:8088>.

Run it again and the existing demo data stays in place. This command does not create the 100,000-row dataset.

```powershell
python start.py --reset
```

`--reset` drops the demo database tables and loads the small dataset again.

Check the API without leaving it running:

```powershell
python start.py --no-serve
```

Verify the acceptance behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The checks use a separate `audi_test` database. Start PostgreSQL first with `python start.py --no-serve` if it is not already running.

## Actors

There is no login screen. Send `X-Actor-Token` on every tenant-scoped request.

| Actor | Tenant | Time zone | Token |
| --- | --- | --- | --- |
| alice@east.test | East | Australia/Sydney | `east-alice` |
| bob@west.test | West | Australia/Perth | `west-bob` |

`GET /api/actors` returns the same demo actors for the future actor switcher.

## Demo data

Both tenants have a course titled Safety 101 and three learners:

| Learner | Enrollment | Certificate |
| --- | --- | --- |
| Alex Lee | completed | already issued |
| Casey Ng | completed | not issued; eligible for bulk issue |
| Drew Kim | incomplete | none |

Alex Lee's certificate was issued at `2026-01-10T13:30:00Z`.

- East displays `2026-01-11 00:30`.
- West displays `2026-01-10 21:30`.

List sorting uses that tenant-local calendar date. Rows with the same date are ordered by certificate id ascending, including when the date sort itself is descending.

## API

- `GET /api/certificates?q=&sort=&order=&page=&page_size=`
- `GET /api/certificates/{id}`
- `POST /api/certificates/bulk-issue` with header `Idempotency-Key` and body `{"course_id":"..."}`
- `POST /api/certificates/{id}/revoke`
- `GET /api/courses`

`sort` is one of `learner_name`, `serial_number`, `issued_date`, `course_title`, `status`. `order` is `asc` or `desc`. Search matches learner name or serial number inside the caller's tenant.

Bulk issue returns one row per enrolled learner: `issued`, `skipped` (`not_completed` or `already_certified`), or `failed`. The same key and payload always return that same result. The same key with a different payload returns 409. A course outside the caller's tenant returns 404 and creates nothing.

Revoking an active certificate writes one `revoked` audit. Repeating the revoke leaves that audit as it is.

## Reproduce the acceptance checks

Set the base URL and then call the API:

```powershell
$base = "http://127.0.0.1:8088"
```

A1. Tenant isolation. Bob's list contains only `WEST-SAFETY-ALEX`. This detail request returns 404:

```powershell
curl.exe -H "X-Actor-Token: west-bob" "$base/api/certificates/cert-east-alex"
```

This bulk issue also returns 404, and East still has one certificate:

```powershell
curl.exe -X POST -H "X-Actor-Token: west-bob" -H "Idempotency-Key: bob-east" -H "Content-Type: application/json" -d '{"course_id":"course-east-safety"}' "$base/api/certificates/bulk-issue"
```

A2. Retry safety. Send the same East bulk issue twice, sequentially, with the same `Idempotency-Key`. Both responses match. Casey Ng has one certificate and one `issued` audit. Overlapping calls are covered by `pytest` (`test_concurrent_same_idempotency_key_issues_once`).

A3. Key misuse. After A2, repeat the call with the same key and `course_id` set to `course-west-safety`. The response is 409. Call the original body again and the first result is unchanged.

A4. Learner outcomes. The first East bulk issue for Safety 101 issues Casey Ng, skips Alex Lee as `already_certified`, and skips Drew Kim as `not_completed`.

A5. Local time. East detail for `cert-east-alex` shows `2026-01-11 00:30`. West detail for `cert-west-alex` shows `2026-01-10 21:30`. Both UTC values are `2026-01-10T13:30:00Z`.

A6. Export growth. Not implemented.

A7. Revocation audit.

```powershell
curl.exe -X POST -H "X-Actor-Token: east-alice" "$base/api/certificates/cert-east-alex/revoke"
```

The first response has `"changed": true` and one `revoked` audit. Send it again: `"changed": false` and still one `revoked` audit. Alice revoking `cert-west-alex` returns 404.

## Not finished

- Vue 3 screens for the actor switcher, list, bulk issue, and revoke confirmation
- CSV export, including a stable export of 100,000 rows while the list is still being read
- A generator that adds 100,000 East certificates without changing this demo dataset
- AI session exports, `ai/session-index.csv`, `ai/decision-log.md`, and the completeness declaration
- The answers in `written-answers.md` (those are written without AI)
