# 03: Security Invariants, Inbound Dispatch & Outbound RPC

**What to build:** Implement security invariants and communication methods in `aios_gateway.py`. Build `handle_inbound(method, path, headers, raw_body) -> GatewayResult` which encapsulates Bearer token checks, HMAC-SHA256 signature verification over the canonical string `f"{timestamp}:{nonce}:{method.upper()}:{path}:{body_sha256}"`, clock-skew bounding (`<= 300s`), sliding-window anti-replay cache validation, JSON-RPC method dispatch, sequence advancement, and ACK envelope formatting. Build `send_rpc(target_url, method, params, timeout, idempotency_key)` which signs headers and dispatches outbound calls via the `GatewayTransport` seam. Implement cron operations (`list_crons`, `update_cron`, `trigger_cron`, `delete_cron`) and task history operations (`list_tasks`, `record_task`).

**Blocked by:** 01, 02

**Status:** closed

- [x] Implement canonical string computation and HMAC-SHA256 verification
- [x] Implement clock-skew rejection (`> 300s`) and duplicate nonce rejection within TTL window
- [x] Implement `handle_inbound(method, path, headers, raw_body) -> GatewayResult`
- [x] Implement `send_rpc(target_url, method, params, timeout, idempotency_key) -> GatewayResult`
- [x] Implement cron management methods (`list_crons`, `update_cron`, `trigger_cron`, `delete_cron`) using `GatewayStorage`
- [x] Implement task history methods (`list_tasks`, `record_task`) using `GatewayStorage`
- [x] Provide safe built-in command handlers (`ping`, `audit_invariants`, etc.) without host file mutation
