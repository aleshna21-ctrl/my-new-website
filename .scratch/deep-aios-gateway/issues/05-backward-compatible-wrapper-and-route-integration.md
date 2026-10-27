# 05: Backward-Compatible Supervisory Wrapper & Route Integration

**What to build:** Refactor `hud/gateway.py` into a thin backward-compatible supervisory wrapper delegating to an authoritative `AIOSGateway` default instance. Retain all legacy function signatures (`verify_gateway_request`, `compute_signature`, `execute_gateway_rpc`, `execute_task_command`, `load_cron_registry`, `update_cron_job`, `trigger_cron_job`, `delete_cron_job`, `load_task_history`, `record_task_history`, `send_signed_rpc`). Bind legacy global singletons (`GLOBAL_NONCE_CACHE`, `GLOBAL_SYNC_TRACKER`, `GLOBAL_FEEDBACK_LOOP`, `GLOBAL_IDEMPOTENCY_REGISTRY`) to the default instance. Verify that `hud/routes/gateway_routes.py` and `hud_server.py` continue functioning seamlessly and that all 18 existing tests in `tests/test_hermes_gateway.py` pass without modification.

**Blocked by:** 01, 02, 03, 04

**Status:** closed

- [x] `hud/gateway.py` initializes a default `AIOSGateway` instance with `DiskGatewayStorage` and `UrllibTransport`
- [x] Connects `hermes.board.*` method handlers dynamically via `register_method()`
- [x] Preserves all legacy module-level functions with exact arguments
- [x] Preserves legacy global singletons mapped to the default instance
- [x] `hud/routes/gateway_routes.py` functions without modification
- [x] All 18 tests in `tests/test_hermes_gateway.py` pass without modification
- [x] Full repository test suite passes with zero regressions
