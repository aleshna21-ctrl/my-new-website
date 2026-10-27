# 04: Deterministic In-Memory Fake AIOS Gateway

**What to build:** Implement `FakeAIOSGateway` in `aios_gateway.py`. The test double initializes with `InMemoryGatewayStorage` and `InMemoryTransport` by default. It provides microsecond execution latency, zero disk I/O, zero network sockets, full call inspection (`calls: List[dict]` and `sent_requests: List[dict]`), canned response mapping (`mock_responses: Dict[str, Any]`), and fault injection (`should_fail: bool`, `fail_error: str`). Add comprehensive unit tests in `tests/test_deep_aios_gateway.py` verifying all security invariants, storage operations, and transport handling through the fake and real seams.

**Blocked by:** 01, 02, 03

**Status:** closed

- [x] Implement `FakeAIOSGateway` inheriting or wrapping `AIOSGateway`
- [x] Uses `InMemoryGatewayStorage` and `InMemoryTransport` by default
- [x] Tracks all inbound and outbound invocations in `calls`
- [x] Supports fault injection via `should_fail` and `fail_error`
- [x] Supports canned method responses via `mock_responses`
- [x] Create `tests/test_deep_aios_gateway.py` covering:
  - [x] HMAC verification and tamper rejection
  - [x] Clock skew rejection (> 300s)
  - [x] Nonce replay rejection
  - [x] Inbound request dispatch and ACK generation
  - [x] Outbound RPC dispatch over `InMemoryTransport`
  - [x] Cron registry listing, updating, triggering, and deletion in memory
  - [x] Fault injection behavior
