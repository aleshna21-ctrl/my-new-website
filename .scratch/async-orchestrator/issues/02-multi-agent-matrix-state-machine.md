# 02: Hardened Multi-Agent Matrix State Machine

**What to build:** Implement the hardened multi-agent state machine in `AsyncOrchestrator` driving tasks across defined matrix paths via `JobLedger.claim_job()` and `JobLedger.update_job_state()`. Enforce strict 1-active-agent concurrency locking, persona prompt framing via `HermesAdapter`, code extraction from markdown blocks, ephemeral sandbox execution via `EphemeralSandboxRunner`, and state transitions across Ingestion, Synthesis, Code Path, and Content Path to `[ DONE ]`.

**Blocked by:** 01: Authoritative Async Orchestrator Seam & Response Contracts

**Status:** closed

- [x] Enforces concurrency lock: checks no other task is in `[ ACTIVE_* ]` before claiming new tasks
- [x] Ingestion flow: `[ NEW_PAYLOAD ]` -> boundary-enforcer -> `[ PAYLOAD_CLEAN ]` -> structural-extractor -> `[ SYNTHESIS_PENDING ]`
- [x] Logic branching: `[ SYNTHESIS_PENDING ]` -> logic-synthesizer -> `[ NEEDS_CODE ]` or `[ NEEDS_CONTENT ]`
- [x] Code Path: `[ NEEDS_CODE ]` -> systems-engineer -> `[ BLUEPRINT_READY ]` -> code-fabricator -> Ephemeral Sandbox execution -> `[ DONE ]`
- [x] Content Path: `[ NEEDS_CONTENT ]` -> content-drafter -> `[ DRAFT_READY ]` -> boundary-enforcer -> `[ DRAFT_VERIFIED ]` -> execution-dispatcher -> `[ DONE ]`
- [x] All database writes delegate strictly across `JobLedger`
- [x] All model inferences delegate strictly across `HermesAdapter`
