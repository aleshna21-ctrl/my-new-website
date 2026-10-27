---
status: accepted
date: 2026-10-27
---

# Deepen the AIOS Gateway and Two-Way Communication Seam

We encapsulate HMAC authentication, sliding-window anti-replay filtering, sequence tracking, cron/task registry persistence, and bidirectional JSON-RPC 2.0 dispatch behind an authoritative, deep `AIOSGateway` module with pluggable storage and transport seams.

## Context and Decision

Previously, `hud/gateway.py` spanned 1,023 lines coupling five distinct operational concerns:
1. **Mutable Global State**: Exposed module-level singletons (`GLOBAL_NONCE_CACHE`, `GLOBAL_SYNC_TRACKER`, `GLOBAL_FEEDBACK_LOOP`, `GLOBAL_IDEMPOTENCY_REGISTRY`), preventing concurrent multi-instance isolation and causing cross-test state pollution.
2. **Raw Disk File I/O & Locks**: Handled cron job definitions and task execution histories by directly writing to `data/cron_registry.json` and `data/gateway_tasks.json` with process-wide threading locks, preventing socketless and diskless unit testing.
3. **Unabstracted Network Socket Transport**: Initiated outbound JSON-RPC calls via unmockable `urllib.request` HTTP sockets directly inside `send_signed_rpc`, requiring live loopback ports or complex monkey-patching for tests.
4. **Side-Effect Leakage in Command Handlers**: Hardcoded task execution commands (e.g. `second_brain_scan`) directly invoked host filesystem scripts, inadvertently triggering full GTM migrations and writing files to Google Drive paths during unit tests.
5. **Coupling to Dashboard Subsystems**: Methods such as `hermes.board.mutate` directly imported `hud/os_dashboard.py`, tying the gateway to specific front-end file formats and calendar logic.

We extract two-way gateway communication into an authoritative deep `AIOSGateway` module:
1. **Authoritative Gateway Seam**: Exposes a clean, consolidated interface (`handle_inbound()`, `send_rpc()`, `crons()`, `tasks()`, `health()`) governing all two-way communication between the operator cockpit and autonomous reasoning agents.
2. **Instance-Level State Encapsulation**: Encapsulates the anti-replay sliding-window cache, synchronization sequence counter, and RTT feedback tracking inside the `AIOSGateway` instance, with singleton exposure maintained only at the backward-compatibility layer.
3. **Pluggable Storage Seam**: Accepts an abstract `GatewayStorage` adapter with two concrete implementations: `DiskGatewayStorage` (atomic JSON persistence in production) and `InMemoryGatewayStorage` (isolated dictionary storage for tests).
4. **Pluggable Transport Seam**: Accepts an injectable `GatewayTransport` seam with two concrete implementations: `UrllibTransport` (live HTTP sockets in production) and `InMemoryTransport` (socketless loopback and canned response recording for tests).
5. **Pluggable Command and Method Registry**: Decouples execution from host scripts via `register_command()` and `register_method()`, providing safe built-in defaults (`ping`, `audit_invariants`) while allowing external subsystems to attach domain handlers without circular dependencies.
6. **Dual Response Contracts**: `GatewayResult(dict)`, `CronJobSnapshot(dict)`, and `TaskExecutionSnapshot(dict)` inherit from `dict` for 100% wire and attribute compatibility across routes and tests.
7. **Deterministic In-Memory Test Double (`FakeAIOSGateway`)**: Operates entirely in memory with microsecond latency, zero socket allocation, zero disk side-effects, audit logging (`calls`), and fault injection (`should_fail=True`).
8. **Backward-Compatible Supervisory Wrapper**: Retains `hud/gateway.py` as a delegating shell exposing all legacy helper functions and singleton caches so existing route handlers and scripts continue functioning without modification.

## Consequences

- All gateway routes and client scripts interact across a unified, deep seam.
- Tests run completely socketless and diskless without polluting the host filesystem or triggering external scripts.
- Replay attacks, signature tampering, and clock-skew anomalies are trapped and verified within a single authoritative module.
