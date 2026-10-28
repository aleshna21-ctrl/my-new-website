# ADR-0007: Hermes Agent Observability, Efficacy Scoring & Multi-Tier Visualization

## Status
accepted

## Context
As the AI Operating System orchestrates autonomous multi-agent pipelines across `AsyncOrchestrator`, `HermesAdapter`, and `JobLedger`, operators require real-time visibility into agent activities, operational efficacy metrics, and direct intervention controls within the HUD cockpit. Previously, model metrics in `inference_telemetry.json` were disconnected from task lifecycle states in `job_ledger.db` and anomaly tracking in `invoice_quarantine.py`, making it difficult to distinguish model hallucination from database lock contention or invariant violations.

## Decision
1. **Canonical Domain Boundary**: Define **Hermes Agent** as an `AsyncOrchestrator`-governed worker executing matrix tasks via `HermesAdapter` (inference) and recording state transitions in `JobLedger` (persistence). Standardize the multi-agent topology across 4 canonical lifecycle roles: `Triage`, `Scout & Auditor`, `Execution Agent`, and `Supervisor & Gatekeeper`.
2. **Composite Agent Efficacy Score**: Quantify agent efficacy on a 0.00 – 1.00 index combining Inference Health (35%, based on schema repairs and latency SLA), Invariant Integrity (35%, based on clean invariant compliance), and Gatekeeper Confidence (30%, based on auto-execution approvals). Enforce a hard ceiling capping efficacy at $\le 0.40$ whenever an agent triggers an invoice quarantine incident or stalled lock ejection.
3. **Single-Pipe Telemetry Transport**: Stream live agent step activity, thought loops, and efficacy frames to the AI OS interface over the existing `/api/os/stream` Server-Sent Events (SSE) backbone and `AIOSGateway` dispatcher, eliminating redundant WebSocket servers.
4. **Interactive Control Plane**: Provide four immediate operator interventions through `AIOSGateway`: Queue Pause/Resume, Model Tier Fallback, Quarantine Auto-Remediation, and Stalled Lock Eviction.
5. **Three Iterative Prototypes & AI OS Drawer**: Deliver three sequential prototypes linked via a 6-item prototype switcher ribbon (`prototype-4-hermes-stream.html` for high-frequency activity stream, `prototype-5-hermes-matrix.html` for topological DAG interaction, and `prototype-6-hermes-cockpit.html` for unified efficacy governance), integrated into `static/os.html` as the `🤖 Hermes Agents` drawer.

## Consequences
- Operators gain sub-second visibility into whether an underperforming agent suffers from prompt drift (repaired by `HermesAdapter`), invariant failures (trapped by `Quarantine`), or low decision confidence.
- Testing remains fast, socket-free, and deterministic through `FakeHermesAdapter`, `FakeJobLedger`, and `FakeAIOSGateway`.
- Front-end dashboards remain strictly CSP-compliant without ad-hoc external socket dependencies.
