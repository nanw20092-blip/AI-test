# Written technical answers

Complete this file yourself, without AI assistance. Do not use an AI tool to draft, outline, translate, rephrase, or edit the answers.

## 1

A service stores user names in users.display_name. A proposed release introduces users.full_name, changes all application reads and writes to the new column, and drops display_name in the same deployment. The service uses rolling deployment, so old and new application instances run concurrently. The release must also support rollback. Explain why this release can fail and propose a safe sequence of database and application changes.

The release fails because rolling deployment means old and new app instances run at the same time. Old instances still read/write display_name. If display_name is dropped in the same deployment, old instances will hit SQL errors. Also, after dropping the column, rollback to old version is impossible, as old code requires display_name.

Safe sequence:

1. Add full_name column and backfill data from display_name. Keep all app code unchanged.
2. Deploy new version with dual-write logic: writes update both columns; reads use full_name with fallback.
3. Deploy another release to switch all reads and writes to only use full_name. Leave display_name in table.
4. After confirming stability and rollback window closed, drop the display_name column.

## 2

Certificate details are cached for 60 seconds. Request A misses the cache and reads ACTIVE from the database. Before A writes to the cache, request B revokes the certificate, commits the database transaction, and deletes the cache entry. A then writes its stale ACTIVE value into the cache. A colleague proposes reducing the cache TTL to five seconds. Explain why this does not fix the problem. Redesign the read and revocation paths so that any read starting after B returns success cannot receive the stale ACTIVE value.

Reducing TTL only shortens the window during which stale data is served. It does not eliminate the race condition. The race happens because request A fetches an ACTIVE snapshot from DB, then gets preempted; revocation B deletes cache, then A later writes the stale ACTIVE back. Even with 5s TTL, stale data can still be written and served for up to 5 seconds.

Redesign option (version based):
Add a version column to certificates, increment on every status change.
Read path: On cache miss, fetch status + version from DB. Before writing back to cache, compare the fetched version against current DB version. Discard the write if versions do not match.
Revocation path: Update status to REVOKED, increment version, commit transaction, delete cache key.

## 3

Service A has 50 request workers. Every request to its /report endpoint calls Service B with a 100 ms timeout and up to three retries. Traffic to /report remains at 1,000 requests per second. B's latency suddenly rises from 20 ms to 2 seconds, and unrelated endpoints on A soon stop responding. Explain the chain of failure, including the effect of retries. Redesign /report so unrelated endpoints remain available, and state what /report should return when B is unhealthy.

All 50 workers are shared across all endpoints of Service A. Each /report request calls B with a 100ms timeout and up to 3 retries. When B slows down, each outbound call times out after 100ms while holding a worker. Retries increase the total worker hold time per /report request. At 1000 rps, workers are consumed faster than they can be released. Eventually all 50 workers are stuck waiting for calls to B. No workers remain to handle unrelated endpoints, so they stop responding. Retries amplify resource consumption and accelerate worker exhaustion.

Redesign: Apply bulkhead isolation. Create a separate limited worker pool only for /report, so its blocking calls cannot consume workers reserved for other endpoints. Add a circuit breaker for Service B: when failure rate exceeds threshold, open the circuit and stop calling B and stop retries.

When B is unhealthy, /report should fail fast and return 503 Service Unavailable (or a graceful degraded response), without blocking or retrying.