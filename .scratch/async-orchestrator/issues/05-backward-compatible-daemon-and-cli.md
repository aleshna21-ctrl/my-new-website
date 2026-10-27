# 05: Backward-Compatible Daemon Wrapper & CLI Integration

**What to build:** Refactor `async_orchestrator_daemon.py` to become a thin, backward-compatible supervisory wrapper delegating to `AsyncOrchestrator`. Retain the existing `AsyncOrchestratorDaemon` class interface, command-line arguments (`--once`, `--interval`, `--model`, `--endpoint`), loopback worker threads, and OS signal handling (`SIGINT`, `SIGTERM`), ensuring all 240 existing repository tests pass without modification.

**Blocked by:** 01, 02, 03

**Status:** closed

- [x] `async_orchestrator_daemon.py` delegates core orchestration logic to `AsyncOrchestrator`
- [x] Retains `AsyncOrchestratorDaemon` class with existing methods (`run_sync_loop()`, `poll_and_process_once()`, `stop()`)
- [x] Preserves all CLI flags (`--once`, `--interval`, `--model`, `--endpoint`, `--verbose`)
- [x] Preserves clean signal handling and shutdown hygiene on Windows
- [x] All existing test suites pass: `tests/test_async_orchestrator_daemon.py`, `tests/test_sandboxed_durable_execution.py`, `tests/test_hardened_state_machine.py`
