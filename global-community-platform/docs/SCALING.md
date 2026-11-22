# Performance & scaling

This page records what was measured, what was changed, and what it takes to serve very
large audiences. Numbers come from `apps/common/test_performance.py` and a load test run
on a 4-core development laptop (SQLite, Django dev data); treat them as relative, not as
production capacity.

## What was measured and fixed

| Problem found | Before | After |
|---|---|---|
| Feed loaded every like/comment/bookmark row just to count them | 480 ms with 600 likes per post; timed out (>5 min) at 3,000 | **28 ms** and **37 ms** |
| Trending counted by joining likes × comments × bookmarks (row explosion) | 12,958 ms with 600 likes per post | **32 ms**; **52 ms** at 3,000 likes |
| Visibility rules joined community memberships and needed `DISTINCT` | extra sort/dedupe on every feed query | `EXISTS` subquery, no `DISTINCT` |
| Page-number paging runs `COUNT(*)` and `OFFSET` scans on every page | cost grows the deeper you scroll | **cursor paging** for the home feeds: same cost on page 1 or 10,000 |
| Block/mute lists queried on almost every request | 2 queries per request | cached per user, invalidated instantly on change |
| Unread-count polling every 45 s per open tab | ~22,000 requests/s at 1 M users | every 5 min + on reconnect (~3,300/s); live pushes do the rest |
| Media streamed through Python workers | ties up a worker per download | `MEDIA_ACCEL_REDIRECT_PREFIX`: Django authorises, nginx streams |
| Photos uploaded at full size | 19.6 MB for two phone photos | **2.6 MB** (shrunk in the browser) |

Query counts per request stay flat as data grows (guarded by `QueryBudgetTests`):
home feed 5, following 5, trending 6, story tray 14, profile 13, notifications 1.

### Load test (production server: gunicorn + uvicorn workers)

Mixed traffic (feed, trending, story tray, unread count), JWT-authenticated, 15 s per run,
load generator on the same laptop:

| Concurrent users | 1 worker | 4 workers |
|---|---|---|
| 10 | 30 req/s · p50 373 ms | 80 req/s · p50 121 ms · p95 227 ms |
| 50 | 27 req/s · p50 1.9 s | 84 req/s · p50 395 ms |
| 100 | 27 req/s · p50 4.1 s | 74 req/s · p50 1.3 s |

Zero errors in every run. Throughput scales with workers (≈2.7× on 4 cores, sharing the
CPU with the load generator). In-process, a feed request costs ~23 ms of CPU and an unread
count ~3 ms.

## Capacity, honestly

The app servers are stateless (sessions are JWT + Redis-backed tickets), so capacity grows
by adding servers. Rough sizing: an active user makes ~1 API request every 10 s, so
**1 million concurrent users ≈ 100,000 requests/s**. At ~40 feed requests/s per core that is
a few thousand cores before caching. Code alone cannot promise "millions at once"; the
architecture below can be scaled to it, and the measurements above tell you the cost.

## Production setup included

- `deploy/gunicorn.conf.py`: uvicorn workers (HTTP + WebSockets), worker recycling.
- `deploy/nginx.conf`: TLS, HTTP/2, gzip, immutable caching of built assets, WebSocket
  proxying, protected media via `X-Accel-Redirect`, and edge rate limits (30 req/s per IP,
  10 logins/min per IP).
- `DJANGO_ENV=production` refuses to start without a secret key, hosts, CORS/CSRF origins,
  `DATABASE_URL` (PostgreSQL) and `REDIS_URL`, and turns on HTTPS redirect, HSTS, secure
  cookies, no-sniff, `X-Frame-Options: DENY` and a strict referrer policy.
- Database connections are persistent with health checks.

## Next steps as traffic grows

1. **PostgreSQL** (required in production) with **PgBouncer**; add **read replicas** for feeds.
2. **Redis** (required) for cache, Channels, throttles and WebSocket tickets; use a Redis
   cluster once one instance is busy.
3. **Object storage + CDN** for media (S3-compatible bucket; signed URLs from the CDN instead of
   nginx), so media bandwidth never reaches app servers.
4. **Background workers** (Celery/RQ) for image processing, notification fan-out and story
   purging, so uploads return immediately.
5. **Precomputed timelines** for the Following feed (fan-out on write for most users, fan-out
   on read for very large accounts), which is how large social apps keep feeds fast.
6. **Cache trending** globally for a minute and filter per viewer.
7. **Search** with PostgreSQL full-text search, then OpenSearch.
8. **Observability:** request timing, slow-query logs, error tracking, and alerts on p95
   latency, before you need them.
