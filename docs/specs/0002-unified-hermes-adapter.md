# Specification: Unified Hermes Model Adapter & Test Substitutability

**Status**: Ready for Agent (`ready-for-agent`)  
**Associated ADR**: [0002-unified-hermes-adapter.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0002-unified-hermes-adapter.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)

---

## Problem Statement

In the AIOS architecture, interaction with the local Hermes LLM runtime was fragmented across multiple layers of the system. Model endpoint resolution, live socket probing against `/v1/models`, concurrency locks, 15-second TTL cache management, and telemetry persistence were duplicated across the server routing layer, a background probe class, and the inference adapter.

Furthermore, testing components that depended on model execution required fragile monkey-patching of Python's low-level socket and URL opening libraries (`urllib.request`). When endpoints were offline or when schema validations failed, callers lacked a unified, authoritative interface for querying the model, inspecting health, or verifying bounded repair invariants.

---

## Solution

Consolidate all local model communication, live socket probing, bounded schema repair, and telemetry persistence behind a unified, deep adapter module. The adapter exposes a two-method seam:

1. `query(prompt, schema=None, allow_simulation=False)`: Executes raw textual completions or schema-enforced structured extraction with bounded single-retry repair and atomic telemetry recording.
2. `health(probe_live=False, ttl=15.0)`: Thread-safe socket probe against local model endpoints with encapsulated TTL caching and telemetry ingestion.

To provide first-class test substitutability, the system provides two implementations of this seam:
- `LiveLocalModelAdapter`: Production HTTP client communicating with the local runtime.
- `FakeHermesAdapter`: In-memory test double supporting canned completions, configurable reachability states, simulated delays, and an audit trail of calls without touching the network.

---

## User Stories

1. As an operator observing the HUD Interface, I want to see the live reachability status and model catalog of the local Hermes runtime without delaying the main dashboard render loop.
2. As an operator observing the HUD Interface, I want health checks to be cached for 15 seconds across concurrent dashboard clients so that loopback sockets are not overwhelmed by redundant requests.
3. As an operator observing the HUD Interface, I want visual clarity on whether the latest model run was live or simulated so that synthetic fallback data is never mistaken for genuine inference.
4. As an operator executing a manual diagnostic probe, I want the system to reject concurrent probe requests with HTTP 409 Conflict if a probe is already running.
5. As an autonomous reasoning agent dispatched via the AIOS Gateway, I want structured JSON extraction that is validated strictly against Pydantic contracts so that malformed data never enters downstream pipelines.
6. As an autonomous reasoning agent, I want a single bounded repair retry when the model emits malformed JSON so that minor syntax errors can be repaired without risking unbounded token consumption.
7. As an autonomous reasoning agent, I want model outputs that fail schema validation after the bounded repair attempt to be placed immediately into Quarantine so that data integrity is maintained.
8. As a developer writing integration tests for AIOS Gateway tasks, I want to substitute an in-memory `FakeHermesAdapter` so that tests execute deterministically and fast without requiring a running model daemon.
9. As a developer writing tests, I want `FakeHermesAdapter` to record an audit log of all invocations so that I can assert prompt formats and schema specifications without mocking network calls.
10. As a developer writing tests, I want to configure `FakeHermesAdapter` to simulate model reachability failures so that I can verify error handling and quarantine logic under controlled conditions.
11. As a security auditor, I want the model adapter to reject cloud endpoints, external IP addresses, credentials in URLs, and query parameters so that inference never leaks across the network boundary.
12. As a data pipeline consumer, I want reasoning tokens (`<think>` tags) and markdown code fences stripped automatically from model responses before schema validation is evaluated.
13. As an offline telemetry auditor, I want all inference results to be persisted atomically to `inference_telemetry.json` using temporary files and filesystem sync so that partial writes are impossible.
14. As an existing subsystem invoking legacy helper methods, I want `enforce_schema_and_quarantine()` and `call_local_server()` to remain fully functional by delegating to the unified seam.
15. As an observer querying model status, I want token usage, latency measurements, and model IDs captured on every run for operational visibility.

---

## Implementation Decisions

### 1. Authoritative 2-Method Seam

All interactions with the model runtime flow through two primary methods:

```python
class ModelAdapter(Protocol):
    def query(self, prompt: str, schema: Optional[Type[BaseModel]] = None,
              allow_simulation: Optional[bool] = None) -> InferenceResult: ...

    def health(self, probe_live: bool = False, ttl: float = 15.0) -> HermesHealth: ...
```

### 2. Dual Deep Response Contracts

To maintain complete backward compatibility with existing dictionary consumers while providing strongly-typed property access:
- **`InferenceResult(dict)`**: Returns standard status (`validated_live`, `validated_simulation`, `quarantined`, `completed`, `error`), validated `data`, `attempts` history, `latency_ms`, and `raw_content`.
- **`HermesHealth(dict)`**: Returns `reachable` (`live_loopback_reachable`), `models` list, `state`, `latency_ms`, `live_probe_detail`, and merged `telemetry` snapshot.

### 3. Encapsulated Probe Concurrency and TTL Caching

- The probe concurrency lock (`threading.Lock`) and TTL cache timestamps are encapsulated directly inside the adapter instance rather than managed globally by callers.
- Calling `health(probe_live=False, ttl=15.0)` returns cached state within the TTL window without opening new loopback sockets.
- Calling `health(probe_live=True)` bypasses the cache, queries `/v1/models` within 1.5 seconds, and updates the cache.

### 4. Bounded Single-Retry Repair Loop

- Maximum retries are bounded between 0 and 1 (default 1). Attempts beyond 1 are rejected at configuration time.
- If attempt 1 fails schema validation, attempt 2 presents the previous output and specific validation error for repair.
- If attempt 2 fails, the output is marked `quarantined` and data is set to `None`.

### 5. Atomic Telemetry Persistence

- Writes to `inference_telemetry.json` are performed via `NamedTemporaryFile` followed by `flush()`, `os.fsync()`, and `os.replace()`.
- Readers never observe partially written files.

### 6. Elimination of Redundant Probes

- The standalone probe in the server background thread delegates directly to `LiveLocalModelAdapter.health()`.
- Server routes (`/api/hermes`, `/api/hermes/probe`) interact solely with the adapter interface.

---

## Testing Decisions

### What Makes a Good Test

- Tests must exercise external behavior across the seam (`query` and `health`) or the HTTP boundary (`/api/hermes`, `/api/hermes/probe`), never internal private helper methods.
- Tests must verify that `FakeHermesAdapter` can be cleanly swapped for `LiveLocalModelAdapter` across the seam without modifying caller code.
- Telemetry file writes must be isolated to temporary directories during tests.

### Target Modules

- `inference_adapter.py` (Unit tests for seam methods, bounded repair, TTL caching, atomic persistence, `FakeHermesAdapter`).
- `hud/hermes.py` (Verification that probe delegation operates transparently).
- `hud_server.py` & `hud/routes/gateway_routes.py` (Verification that HTTP endpoints return expected schema envelopes).

### Prior Art

- `tests/test_deep_hermes_adapter.py`: Dedicated unit test suite verifying seam methods, bounded repair, TTL caching, and `FakeHermesAdapter` substitutability.
- `tests/test_hermes_adapter_dashboard_integration.py`: End-to-end integration tests between adapter telemetry and AIOS dashboard frames.
- `tests/test_probe_alignment.py`: Regression tests for probe concurrency lock, simulation isolation, and port binding.

---

## Out of Scope

- Remote or multi-tenant cloud model providers (OpenAI, Anthropic, Google Cloud Vertex). The adapter strictly refuses non-loopback endpoints.
- Unbounded repair dialogues. The maximum retry budget is strictly capped at 1.
- Streaming token completions across Server-Sent Events (SSE). The adapter provides discrete completion and structured validation envelopes.

---

## Further Notes

- All changes maintain 100% wire compatibility with the frontend HUD Interface and pass all 206 repository unit and integration tests.
- When an external issue tracker is connected, this spec is marked with triage label `ready-for-agent`.
