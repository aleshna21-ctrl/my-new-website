---
status: accepted
date: 2026-10-26
---

# Unified Hermes Model Adapter and Test Substitutability

We consolidate local Hermes LLM endpoint resolution, live socket probing, bounded schema repair, and telemetry snapshotting behind a single deep adapter module in `inference_adapter.py`.

## Context and Decision
Previously, Hermes URL resolution, health probing, and telemetry I/O were fragmented across `hud_server.py`, `hud/hermes.py`, `inference_adapter.py`, and `hud/gateway.py`. Callers had to manage probe locks, TTL caching, and telemetry file paths individually. We unified all model interaction behind a 2-method seam (`query` and `health`) and provided two adapters: `LiveLocalModelAdapter` (for production HTTP communication) and `FakeHermesAdapter` (for fast, deterministic in-memory testing).

## Consequences
- Callers and routes (`/api/hermes`, `/api/hermes/probe`) interact solely with the adapter rather than making ad-hoc HTTP calls or reading raw telemetry files.
- Probe throttling and thread-safe socket locking live inside `health()`.
- Tests can substitute `FakeHermesAdapter` without monkey-patching `urllib.request`.
