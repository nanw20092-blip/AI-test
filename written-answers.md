# Written technical answers

Complete this file yourself, without AI assistance. Do not use an AI tool to draft, outline, translate, rephrase, or edit the answers.

## 1

A service stores user names in users.display_name. A proposed release introduces users.full_name, changes all application reads and writes to the new column, and drops display_name in the same deployment. The service uses rolling deployment, so old and new application instances run concurrently. The release must also support rollback. Explain why this release can fail and propose a safe sequence of database and application changes.

## 2

Certificate details are cached for 60 seconds. Request A misses the cache and reads ACTIVE from the database. Before A writes to the cache, request B revokes the certificate, commits the database transaction, and deletes the cache entry. A then writes its stale ACTIVE value into the cache. A colleague proposes reducing the cache TTL to five seconds. Explain why this does not fix the problem. Redesign the read and revocation paths so that any read starting after B returns success cannot receive the stale ACTIVE value.

## 3

Service A has 50 request workers. Every request to its /report endpoint calls Service B with a 100 ms timeout and up to three retries. Traffic to /report remains at 1,000 requests per second. B's latency suddenly rises from 20 ms to 2 seconds, and unrelated endpoints on A soon stop responding. Explain the chain of failure, including the effect of retries. Redesign /report so unrelated endpoints remain available, and state what /report should return when B is unhealthy.
