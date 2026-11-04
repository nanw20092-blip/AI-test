# Certificate Admin Console

Internal admin console for a multi-tenant training platform. Tenant admins list certificates, issue them in bulk, revoke them, and export CSV. There is no login screen.

## Requirements

- Docker, so PostgreSQL can be started locally
- Python 3.12
- Node.js 24 and npm, so the Vue 3 app can be built

## Start

From this directory:

```powershell
python start.py
```

That command creates a virtual environment, installs Python and npm dependencies, builds the Vue app, starts PostgreSQL, loads the demo data when the database is empty, and serves the API and the UI at <http://127.0.0.1:8088>.

Run it again and the existing demo data stays in place. This command does not create the 100,000-row dataset.

```powershell
python start.py --reset
```

`--reset` drops the tables and loads the small demo dataset again. It also removes the 100,000-row dataset.

```powershell
python start.py --no-serve
```

That prepares the database and does not build or serve the UI.

## Verify

```powershell
python verify.py
python verify.py --volume
```

`verify.py` starts PostgreSQL if needed and runs the acceptance checks against a separate `audi_test` database. The plain command covers A1–A5 and A7, plus CSV shape and order. `--volume` generates 100,000 East certificates and checks A6. Plain `pytest` skips that case because it is marked `volume`.

## Actors

Send `X-Actor-Token` on every tenant-scoped request. The page loads the same actors into the switcher.

| Actor | Tenant | Time zone | Token |
| --- | --- | --- | --- |
| alice@east.test | East | Australia/Sydney | `east-alice` |
| bob@west.test | West | Australia/Perth | `west-bob` |

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

List sorting and CSV order use that tenant-local calendar date. Rows with the same date are ordered by certificate id ascending, including when the date sort itself is descending. The CSV issue column is the same local time shown in the UI, `YYYY-MM-DD HH:MM`.

## 100,000 rows

This does not change the seeded Alex, Casey, or Drew rows:

```powershell
.\.venv\Scripts\python.exe scripts\generate_volume.py
```

It adds 100,000 East certificates on Safety 101, all on the same Sydney calendar date. One thousand of them are named Target Lee (the first is `Target Lee, Jr.`). The rest are named Pat Lee. Running it again adds nothing. `python start.py --reset` clears them.

## API

- `GET /api/certificates?q=&sort=&order=&page=&page_size=`
- `GET /api/certificates/export?q=&sort=&order=`
- `GET /api/certificates/{id}`
- `POST /api/certificates/bulk-issue` with header `Idempotency-Key` and body `{"course_id":"..."}`
- `POST /api/certificates/{id}/revoke`
- `GET /api/courses`

`sort` is one of `learner_name`, `serial_number`, `issued_date`, `course_title`, `status`. `order` is `asc` or `desc`. Search matches learner name or serial number inside the caller's tenant. Export uses that same search and sort, without pagination.

Bulk issue returns one row per enrolled learner: `issued`, `skipped` (`not_completed` or `already_certified`), or `failed`. The same key and payload always return that same result. The same key with a different payload returns 409. A course outside the caller's tenant returns 404 and creates nothing.

Revoking an active certificate writes one `revoked` audit. Repeating the revoke leaves that audit as it is.

The UI disables the issue button while a request is in flight and sends one idempotency key for that click. Revoke asks for confirmation. The certificate list has loading, empty, and error states.

## Reproduce the acceptance checks

Open <http://127.0.0.1:8088> or call the API:

```powershell
$base = "http://127.0.0.1:8088"
```

A1. Tenant isolation. Choose Bob in the switcher, or call the API. Bob's list contains only `WEST-SAFETY-ALEX`. This detail request returns 404:

```powershell
curl.exe -H "X-Actor-Token: west-bob" "$base/api/certificates/cert-east-alex"
```

This bulk issue also returns 404, and East still has one certificate:

```powershell
curl.exe -X POST -H "X-Actor-Token: west-bob" -H "Idempotency-Key: bob-east" -H "Content-Type: application/json" -d '{"course_id":"course-east-safety"}' "$base/api/certificates/bulk-issue"
```

Bob's export with the same search does not contain East rows.

A2. Retry safety. Send the same East bulk issue twice, sequentially, with the same `Idempotency-Key`. Both responses match. Casey Ng has one certificate and one `issued` audit. Overlapping calls are covered by `python verify.py` (`test_concurrent_same_idempotency_key_issues_once`). The issue button stays disabled until the request finishes.

A3. Key misuse. After A2, repeat the call with the same key and `course_id` set to `course-west-safety`. The response is 409. Call the original body again and the first result is unchanged.

A4. Learner outcomes. The first East bulk issue for Safety 101 issues Casey Ng, skips Alex Lee as `already_certified`, and skips Drew Kim as `not_completed`. The page shows those three rows.

A5. Local time. East detail for `cert-east-alex` shows `2026-01-11 00:30`. West detail for `cert-west-alex` shows `2026-01-10 21:30`. Both UTC values are `2026-01-10T13:30:00Z`.

A6. Export growth. Generate the 100,000 East rows, then export twice with the same search and sort. `python verify.py --volume` does this against `audi_test`: search `Target`, sort `issued_date` ascending, and requests the certificate list after the first CSV bytes arrive. Each export finishes within 60 seconds. Both files match. The 1,000 Target rows share one local date and stay in certificate id order. To do it by hand against the demo database:

```powershell
.\.venv\Scripts\python.exe scripts\generate_volume.py
curl.exe -H "X-Actor-Token: east-alice" "$base/api/certificates/export?q=Target&sort=issued_date&order=asc" -o east-1.csv
curl.exe -H "X-Actor-Token: east-alice" "$base/api/certificates?q=Alex%20Lee" 
curl.exe -H "X-Actor-Token: east-alice" "$base/api/certificates/export?q=Target&sort=issued_date&order=asc" -o east-2.csv
```

The two CSV files should be identical. The list request can be sent while the first export is still running.

A7. Revocation audit. In the UI, open Alex Lee's East certificate and confirm revoke. Or:

```powershell
curl.exe -X POST -H "X-Actor-Token: east-alice" "$base/api/certificates/cert-east-alex/revoke"
```

The first response has `"changed": true` and one `revoked` audit. Send it again: `"changed": false` and still one `revoked` audit. Alice revoking `cert-west-alex` returns 404.

## Not finished

- `written-answers.md` has the three questions and no answers. Those are written without AI.
- The AI session export in `ai/sessions/` is a snapshot taken while the Cursor session was still open, so the last reply may be missing. Copy the finished transcript over that file before submission if the session continued.
- No git commit was created for the Vue app, export, or volume generator.
