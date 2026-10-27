# AIOS HUD Interface

The operational cockpit, telemetry aggregator, and agent coordination plane for the AI Operating System.

## Language

**HUD Interface**:
The real-time operator cockpit displaying system state, telemetry streams, and agent execution trees.
_Avoid_: Front-end, GUI, portal

**AIOS Gateway**:
The authenticated two-way communication bridge coordinating requests between the operator cockpit and autonomous reasoning agents.
_Avoid_: Proxy, API layer, middleman

**Job Ledger**:
The durable ledger recording state transitions, invariant checks, and execution history for system jobs.
_Avoid_: Database, task log, store

**Quarantine**:
The isolated state holding malformed records and invoice anomalies that fail validation invariants until repaired.
_Avoid_: Dead-letter queue, error bucket

**Hermes Adapter**:
The unified inference adapter governing local model socket connections, bounded schema repair, and telemetry provenance.
_Avoid_: LLM client, model wrapper, AI service

