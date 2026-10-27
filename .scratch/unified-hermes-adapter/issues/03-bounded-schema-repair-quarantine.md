# 03: Bounded Single-Retry Schema Repair & Quarantine Pipeline

**What to build:** Strict Pydantic contract validation and bounded single-retry repair within the model adapter seam. When callers provide a schema, the adapter instructs the model to return conforming JSON. If validation fails on attempt 1, the adapter provides a targeted repair prompt incorporating the validation error for at most one retry. If the repaired output still fails validation, or if network connectivity is absent and simulation is disabled, the payload is immediately placed into Quarantine with `data=None` and full attempt audit history.

**Blocked by:** 01: Authoritative Two-Method Seam & Dual Response Contracts

**Status:** completed

- [x] Model completions strip `<think>` reasoning tags and markdown code fences before JSON extraction
- [x] Successful JSON responses validate strictly against the provided Pydantic model and return `status="validated_live"`
- [x] A malformed first attempt triggers exactly one repair retry with validation error feedback
- [x] Recovery on attempt 2 returns `status="validated_live"` with two recorded attempts in telemetry
- [x] Failure to repair on attempt 2 marks the result `status="quarantined"` and preserves `data=None`
- [x] Max retries parameter is bounded to at most 1; values > 1 are rejected at initialization
- [x] If `allow_simulation` is explicitly True and the endpoint is unreachable, fallback data is clearly marked `is_simulated=True` and `status="validated_simulation"`
- [x] Legacy `enforce_schema_and_quarantine(prompt, schema)` forwards seamlessly to `query(prompt, schema=schema)`
