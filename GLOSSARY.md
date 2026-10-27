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

**Metadata Diode**:
The one-way sanitized outbox export emitting opaque state transition events to notification observers without leaking sensitive payloads or client context.
_Avoid_: Event emitter, message bus, webhook

**Async Orchestrator**:
The autonomous background orchestration engine executing multi-agent matrix pipelines, sandbox execution jails, and stalled lock recovery via the Job Ledger.
_Avoid_: Task scheduler, cron worker, runner daemon


