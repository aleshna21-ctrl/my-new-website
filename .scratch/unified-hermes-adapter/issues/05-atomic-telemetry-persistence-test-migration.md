# 05: Atomic Telemetry Persistence & Test Suite Migration

**What to build:** Atomic telemetry persistence that guarantees readers never see partially written or corrupt telemetry files, coupled with migration of test suites to use the `FakeHermesAdapter` seam. Writes to `inference_telemetry.json` utilize temporary file creation, directory flushing, and atomic file replacement (`os.replace`). Existing AIOS Gateway and dashboard test suites are transitioned away from fragile `urllib.request` socket patching to `FakeHermesAdapter`, verifying all 206 tests remain green.

**Blocked by:** 02: Deterministic In-Memory Test Double (FakeHermesAdapter), 04: Thread-Safe Health Probing, TTL Caching & Route Integration

**Status:** completed

- [x] Telemetry snapshots are written via `tempfile.NamedTemporaryFile` and replaced atomically using `os.replace`
- [x] Telemetry snapshotting creates parent directories on demand and cleans up temporary files on error
- [x] `inference_telemetry.json` output exactly matches expected schema keys (`timestamp_utc`, `endpoint`, `model`, `max_tokens`, `max_retries`, `allow_simulation`, `execution_mode`, `is_simulated`, `status`, `attempts`, `data`)
- [x] Unit test suite verifies seam methods, bounded repair, and `FakeHermesAdapter` without monkey-patching sockets
- [x] Existing dashboard and gateway integration tests run cleanly against the unified adapter seam
- [x] Entire test suite passes without regressions (`python -m pytest -q` -> 211 passed, 14 subtests passed)
