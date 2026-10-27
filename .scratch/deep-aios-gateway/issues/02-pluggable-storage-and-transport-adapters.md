# 02: Pluggable Storage & Transport Seams

**What to build:** Implement pluggable storage and transport seams in `aios_gateway.py`. Define `GatewayStorage` protocol with two concrete implementations: `DiskGatewayStorage` (thread-safe atomic file writes using `.tmp` and `os.replace` for `cron_registry.json` and `gateway_tasks.json`) and `InMemoryGatewayStorage` (isolated in-memory lists/dictionaries for socketless, diskless testing). Define `GatewayTransport` protocol with two concrete implementations: `UrllibTransport` (production HTTP dispatch via `urllib.request`) and `InMemoryTransport` (test double with canned response registration and `sent_requests: List` recording).

**Blocked by:** 01

**Status:** closed

- [x] Define `GatewayStorage` protocol (`load_crons`, `save_crons`, `load_tasks`, `save_tasks`)
- [x] Implement `DiskGatewayStorage` with atomic file writes and thread-safety
- [x] Implement `InMemoryGatewayStorage` initializing with default crons and empty task history
- [x] Define `GatewayTransport` protocol (`send(url, headers, body, timeout) -> (status, headers, body)`)
- [x] Implement `UrllibTransport` with proxy bypass and configurable timeout
- [x] Implement `InMemoryTransport` with `register_response(url_pattern, status, body)` and `sent_requests` recording
