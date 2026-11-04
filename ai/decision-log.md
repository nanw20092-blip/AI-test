# Decision log

Times are Asia/Shanghai (UTC+8). The session file is `ai/sessions/9e15c607-434f-4c36-b505-92157b7a20c5.jsonl`.

Commit `f04a84c` is the backend written in the first part of that session. The Vue app, CSV export, volume generator, and verification command are still uncommitted because commit was not requested.

## Accepted: PostgreSQL and Vue 3

The first plan suggested SQLite and React. The user required PostgreSQL and Vue 3, and that is what was built. PostgreSQL also lets the export keep a read-only server-side cursor open while the certificate list uses another connection.

Verified by `python verify.py` (13 passed) and `python verify.py --volume` (the 100,000-row export test passed). The UI is served from the same process at http://127.0.0.1:8088.

## Corrected: the volume test was calling the API through the system proxy

The first run of the 100,000-row test started uvicorn and then timed out on `/api/health`. The server log said it was listening. `curl.exe` to a server started the same way returned 200, while `httpx` returned 502 or timed out. `httpx` follows the Windows system proxy unless `trust_env=False`. The test was updated to ignore that proxy. The same test then passed in about 9 seconds, including generation, two exports, and a list request issued after the first export bytes arrived. Both CSV bodies matched, and the 1,000 Target rows stayed in certificate id order.

## Tradeoff: one process serves the built Vue app

The documented startup command builds the Vue app and serves it from FastAPI. That is one command for reviewers. `frontend` still has `npm run dev`, which proxies `/api` to port 8088, but that is not the path in the README. The production page has no client-side router, so refreshing `/` does not depend on a history fallback.
