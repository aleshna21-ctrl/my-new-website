# 01: Authoritative Two-Method Seam & Dual Response Contracts

**What to build:** Provide a unified local model adapter seam with two primary operations: `query()` for prompt execution and `health()` for socket reachability inspection. The adapter returns deep response objects (`InferenceResult` and `HermesHealth`) that provide rich attribute access while preserving complete dictionary compatibility for downstream consumers. Local endpoint URLs must strictly enforce loopback hostnames (rejecting external and cloud hosts) and validate parameters at initialization time.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] Adapter exposes `query(prompt, schema=None, allow_simulation=None)` and `health(probe_live=False, ttl=15.0)`
- [x] Endpoint validation strictly permits only local loopback hosts (`127.0.0.1`, `localhost`, `::1`, `hermes`, `host.docker.internal`, `0.0.0.0`) and path `/v1/chat/completions`
- [x] Cloud endpoints (HTTPS, external IPs, credentials in URLs, query parameters) are rejected with `ValueError`
- [x] `InferenceResult` provides property access (`status`, `data`, `raw_content`, `is_simulated`, `attempts`) while functioning as a standard dictionary
- [x] `HermesHealth` provides property access (`reachable`, `models`, `state`, `latency_ms`, `last_status`) while functioning as a standard dictionary
- [x] Unstructured query execution without a schema returns raw completion text wrapped in `InferenceResult`
- [x] Legacy callers invoking `call_local_server` execute cleanly via the adapter
