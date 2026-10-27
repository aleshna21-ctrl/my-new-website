# 04: Thread-Safe Health Probing, TTL Caching & Route Integration

**What to build:** Thread-safe socket health probing with 15-second TTL caching encapsulated directly within the adapter, integrated into HUD routes and background pollers. Probing queries `/v1/models` within 1.5 seconds and returns reachable status and model IDs. Subsequent queries within the 15-second TTL window reuse the cached health status without hitting loopback sockets. Concurrent manual probe requests via `/api/hermes/probe` acquire an isolated probe lock non-blockingly, returning HTTP 409 Conflict if a probe is already running, preventing socket contention and dashboard stream stalls.

**Blocked by:** 01: Authoritative Two-Method Seam & Dual Response Contracts, 03: Bounded Single-Retry Schema Repair & Quarantine Pipeline

**Status:** completed

- [x] `health(probe_live=False, ttl=15.0)` reuses cached `HermesHealth` when invoked within the 15s TTL window
- [x] `health(probe_live=True)` bypasses the TTL cache and executes a live socket check against `/v1/models`
- [x] Internal `_probe_lock` ensures thread-safe cache updates and prevents concurrent socket checks
- [x] `HermesProbe` background worker delegates health checks directly to `adapter.health()`
- [x] `/api/hermes` endpoint queries `adapter.health()` and returns complete telemetry and reachability
- [x] `/api/hermes/probe` endpoint acquires the probe lock non-blockingly, executing `adapter.query()` or returning 409 Conflict if already locked
- [x] Socket timeouts and connection errors are trapped gracefully without raising unhandled exceptions in the server loop
