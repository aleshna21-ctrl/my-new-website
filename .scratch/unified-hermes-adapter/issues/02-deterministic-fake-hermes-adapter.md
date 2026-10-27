# 02: Deterministic In-Memory Test Double (FakeHermesAdapter)

**What to build:** An in-memory test double (`FakeHermesAdapter`) fulfilling the model adapter seam without opening network sockets or invoking HTTP libraries. The fake adapter allows tests across the AIOS Gateway, background workers, and dashboard layers to configure canned completions, reachability states, simulated delays, and custom health responses deterministically. The double maintains an in-memory audit log of all invocations so callers can assert prompt structures and schema validation arguments without socket monkey-patching.

**Blocked by:** 01: Authoritative Two-Method Seam & Dual Response Contracts

**Status:** completed

- [x] `FakeHermesAdapter` implements the identical `query()` and `health()` method signatures
- [x] Configurable with `canned_query_response`, `is_reachable`, `models`, `canned_health`, and `should_fail`
- [x] Schema validation runs against canned responses when a Pydantic schema is passed to `query()`
- [x] Maintains an audit list `calls` recording each invocation method, prompt, schema, and simulation options
- [x] Enables unit tests to swap cleanly for `LiveLocalModelAdapter` without `urllib.request` monkey-patching
- [x] Raises configurable exceptions when `should_fail` is enabled to test system resilience
