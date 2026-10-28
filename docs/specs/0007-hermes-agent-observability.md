# Specification: Hermes Agent Observability, Efficacy Scoring & Multi-Tier Visualization

**Status**: Implemented (`implemented`)  
**Associated ADR**: [0007-hermes-agent-observability.md](file:///c:/Users/alesh/jev-workspace/hud-interface/docs/adr/0007-hermes-agent-observability.md)  
**Domain Glossary Reference**: [GLOSSARY.md](file:///c:/Users/alesh/jev-workspace/hud-interface/GLOSSARY.md)  
**Triage Label**: `ready-for-agent`

---

## Problem Statement

Across the AI Operating System (AIOS), autonomous multi-agent pipelines coordinate reasoning, code execution, and data verification across `AsyncOrchestrator`, `HermesAdapter`, and `JobLedger`. However, operators lacked a cohesive, real-time observability plane into agent operations, effectiveness, and health within the AI OS cockpit.

Specifically:
1. **Disconnected Provenance**: Model inference latency and bounded schema repairs in `inference_telemetry.json` were disconnected from task lifecycle transitions in `job_ledger.db` and anomaly quarantining in `invoice_quarantine.py`. When an agent underperformed or stalled, operators could not distinguish whether the root cause was local model hallucination/schema drift, database lock contention, or invariant violations.
2. **Lack of Quantified Agent Effectiveness**: There was no standard numerical metric evaluating agent performance. Success was treated as a binary outcome rather than an evaluative index reflecting token latency SLA, schema adherence, invariant compliance, and gatekeeper confidence.
3. **Fragmented UI Prototypes**: The existing prototypes in the workspace (`prototype-1-ring-command.html`, `prototype-2-minimal-3d.html`, `prototype-3-cockpit-split.html`) focused on Obsidian 3D graph exploration and static vault views, lacking deep agent stream inspection, DAG interaction topologies, and remediation controls.
4. **No Direct Operator Remediation Plane**: Operators observing degraded agents had no streamlined mechanism in the HUD to pause agent queues, toggle model inference tiers (primary local weights vs. hardened fallback), remediate quarantined records, or evict stalled locks.

---

## Solution

Build an end-to-end observability, efficacy scoring, and visualization suite anchored by ADR-0007, delivering a single-pipe SSE telemetry stream, a composite efficacy evaluation engine, three iterative UI prototypes, and full AI OS dashboard integration.

1. **Canonical Multi-Agent Domain Model**:
   * Canonically define **Hermes Agent** in `GLOSSARY.md` as an `AsyncOrchestrator`-governed worker executing matrix tasks via `HermesAdapter` and persisting state transitions in `JobLedger`.
   * Standardize the agent matrix topology on 4 canonical lifecycle roles:
     * `Triage Agent` (`triage`): Inbound request classification, capability policy validation, and initial dispatch (`actions.ask_jev`).
     * `Scout & Auditor` (`scout`): Targeted vault and filesystem inspection (`jev_file_read`, `jev_multi_file`) with zero context bloat.
     * `Execution Agent` (`exec`): Guarded script execution and code generation under sandboxed jails (`actions.bash_tool`).
     * `Supervisor & Gatekeeper` (`supervisor`): Confidence assessment (`confidence_gate`), readiness evaluation (`composite_score`), and final sign-off.

2. **Composite Agent Efficacy Metric Engine**:
   * Quantify agent efficacy on a composite index $E \in [0.00, 1.00]$:
     $$E = 0.35 \times \text{InferenceHealth} + 0.35 \times \text{InvariantIntegrity} + 0.30 \times \text{GateConfidence}$$
   * **Inference Health**: Evaluated via `HermesAdapter` bounded schema repair frequency and token generation latency against SLA ($< 55\text{ms/tok}$).
   * **Invariant Integrity**: Ratio of clean executions without schema violation or malformed financial records.
   * **Gate Confidence**: Decision confidence score passed to the gatekeeper (`AUTO_EXECUTE` vs `MANUAL_REVIEW`).
   * **Hard Fault Ceiling**: Any incident triggering **Quarantine** or stalled lock ejection in `JobLedger` immediately caps the agent's efficacy score at $\le 0.40$ (degraded state) until resolved.

3. **Single-Pipe Telemetry Transport**:
   * Stream live agent step activity, thought loops, and efficacy frames to the AI OS interface over the existing `/api/os/stream` Server-Sent Events (SSE) backbone and `AIOSGateway` dispatcher, eliminating redundant WebSocket servers and maintaining strict CSP compliance.

4. **Interactive Operator Control Plane**:
   * Expose 4 immediate operator interventions through `AIOSGateway`: Queue Pause/Resume, Model Tier Fallback, Quarantine Auto-Remediation, and Stalled Lock Eviction.

5. **Three Iterative Design Improvement Prototypes**:
   * **Prototype IV — Telemetry & Active Stream Inspector** (`prototype-4-hermes-stream.html`): Sub-second streaming feed of agent thoughts, latency gauges, schema repair diffs, and raw JSON provenance inspection.
   * **Prototype V — Multi-Agent Interaction & Topological Matrix** (`prototype-5-hermes-matrix.html`): Directed acyclic graph (DAG) showing live handoffs between Triage, Scout, Execution, and Supervisor roles, with edge latency, queue hold times, and lock hold monitors.
   * **Prototype VI — Unified Efficacy Command Cockpit** (`prototype-6-hermes-cockpit.html`): Executive command bento combining live stream, topological health, 10-minute sliding efficacy trendlines, StrictStr financial sentinels, and intervention controls.

6. **AI OS Dashboard Integration**:
   * Wire a dedicated `[🤖 Hermes Agents · 0.96 EFF]` header button and `[🤖 Hermes]` dock button in `static/os.html` opening `#drawer-hermes`.
   * Unify all 6 prototypes under a shared 6-item switcher ribbon.

---

## User Stories

1. As an AIOS operator, I want to see a live streaming feed of Hermes agent thoughts and actions, so that I can monitor agent reasoning in real time.
2. As a systems engineer, I want each agent activity card to show its canonical role badge (`[TRIAGE]`, `[SCOUT]`, `[EXEC]`, `[SUPERVISOR]`), so that I can immediately identify which sub-agent is active.
3. As an operator, I want to view the inference latency (ms/token) for each agent step, so that I can identify slow generation speeds before they breach the 55ms SLA.
4. As an operator, I want to monitor token generation throughput (tok/s), so that I know the inference engine is operating at peak performance.
5. As an infrastructure engineer, I want to see whether an agent output required bounded schema repair, so that I can track prompt drift or model regression.
6. As a compliance auditor, I want an Agent Efficacy Score calculated from inference health, invariant integrity, and decision confidence, so that I have a single objective metric for agent effectiveness.
7. As a risk officer, I want any quarantine anomaly or stalled lock ejection to cap the agent's efficacy score at $\le 0.40$, so that data corruption cannot be obscured by fast latency.
8. As a developer, I want to click any event in the stream to inspect its raw JSON payload, prompt hash, and sequence ACK, so that I can audit provenance without digging through log files.
9. As an operator, I want to pause the live stream, so that I can inspect high-frequency events without them scrolling out of view.
10. As an operator, I want to filter the activity stream by specific roles (`Triage`, `Scout`, `Execution`, `Supervisor`), so that I can isolate one subsystem's telemetry.
11. As a QA engineer, I want buttons to inject simulated tasks and simulate schema drift in the prototypes, so that I can demonstrate the UI's reaction to anomalies.
12. As an operator, I want to view a topological DAG of the 4 agent roles, so that I understand how data and intent flow between agents.
13. As an operator, I want animated data pulses traveling along the DAG edges, so that I have immediate visual confirmation of active inter-agent communication.
14. As an operator, I want each DAG node to display its current state (`IDLE`, `PROCESSING`, `HELD_IN_GATE`), so that I know what each agent is doing.
15. As a systems engineer, I want each DAG node to show its active lock duration in `JobLedger`, so that I can detect stalled locks before the automatic sweeper fires.
16. As an operator, I want a direct button to pause an individual role queue, so that I can halt faulty dispatch without shutting down the entire operating system.
17. As an operator, I want a model tier fallback toggle, so that I can switch an agent from primary local weights to hardened fallback weights if accuracy degrades.
18. As an operator, I want a button to forcibly evict a stalled lock, so that orphaned jobs can be unlocked and retried immediately.
19. As an operator, I want a pipeline execution matrix table showing job triggers, execution paths, latencies, and outcomes, so that I can track multi-step workflow completion.
20. As an executive, I want a unified efficacy cockpit (Prototype VI) displaying global system efficacy, so that I can check overall system health in seconds.
21. As an operator, I want a 10-minute sliding window sparkline of efficacy trends, so that I can see whether system performance is improving or degrading over time.
22. As an auditor, I want a dedicated Invariant Sentinel panel verifying StrictStr financial compliance, so that floating-point rounding errors never enter accounts payable.
23. As an operator, I want the Sentinel panel to monitor the Quarantine Vault, so that I know immediately if malformed invoice records are held for repair.
24. As a security officer, I want Level 6 execution jail status clearly displayed, so that I know recursive deletion commands (`rm -rf`) and unauthorized paths are blocked.
25. As a user navigating prototypes, I want a consistent top switcher ribbon across all 6 prototype files, so that I can jump seamlessly between views.
26. As a user of the primary AI OS dashboard (`/os`), I want a `🤖 Hermes Agents` header button, so that I can open the Hermes drawer without leaving my current workspace.
27. As a mobile operator, I want a `🤖 Hermes` dock button in the bottom navigation bar, so that I can access agent telemetry on touch devices.
28. As a frontend security engineer, I want the dashboard to maintain strict Content Security Policy (no inline styles or scripts), so that the application is protected against script injection.
29. As a backend developer, I want all prototype endpoints registered in `hud/routes/static_routes.py`, so that the type-safe router handles static serving cleanly.
30. As an architect, I want canonical terms (`Hermes Agent`, `Agent Efficacy Score`, `Agent Activity Stream`) documented in `GLOSSARY.md`, so that the engineering team shares a unified vocabulary.

---

## Implementation Decisions

### 1. Canonical Domain Boundary and Multi-Agent Matrix
- **Hermes Agent**: A specialized autonomous reasoning worker orchestrated within the matrix that dispatches inference prompts through `HermesAdapter` and logs state transitions in `JobLedger`.
- **4 Canonical Roles**:
  - `Triage`: Inbound request classification and capability verification.
  - `Scout`: Vault and filesystem reading (`actions.jev_file_read`, `actions.jev_multi_file`) returning clean answers with zero added context tokens.
  - `Execution`: Running commands under sandboxed subprocess jails (`actions.bash_tool`).
  - `Supervisor`: Multi-factor readiness index and confidence gate assessment (`composite_score`, `confidence_gate`).

### 2. Composite Efficacy Formulation
The scoring model is implemented as a normalized weighted composite:
```
E = (0.35 * InferenceHealth) + (0.35 * InvariantIntegrity) + (0.30 * GateConfidence)
```
- **Inference Health**: $1.0 - (\text{repairs} \times 0.2 + \text{timeouts} \times 0.4)$
- **Invariant Integrity**: Clean step executions / total executions
- **Gate Confidence**: Average gate confidence score ($0.0 - 1.0$)
- **Penalty Ceiling**: If `invoice_quarantine.count > 0` or `job_ledger.stalled_lock_evictions > 0`, $E = \min(E, 0.40)$.

### 3. Dedicated Static Prototypes
Three iterative HTML prototypes built using Vanilla CSS and JavaScript, adhering to modern dark-theme aesthetics (deep navy `#060911`, cyan `#38bdf8`, emerald `#10b981`, amber `#f59e0b`, purple `#a78bfa`, and gold `#fbbf24`):
- `prototype-4-hermes-stream.html`: High-frequency streaming feed with real-time gauges and raw JSON frame inspector.
- `prototype-5-hermes-matrix.html`: Interactive SVG topological DAG with animated particle edges and per-role intervention controls.
- `prototype-6-hermes-cockpit.html`: 3-column bento command cockpit with global efficacy index, 10-minute sparklines, and governance sentinels.

### 4. AI OS Dashboard Integration (`static/os.html` & `static/os.js`)
- Added `#drawer-hermes` secondary widget drawer in `static/os.html`.
- Added `#trig-hermes` in header widget triggers and `[data-drawer="hermes"]` in the bottom dock.
- Decoupled all drawer styling into `static/os.css` (`.hermes-proto-bar`, `.hermes-roles-grid`, `.role-card-*`) to strictly satisfy CSP requirements (`no style attribute in html`).
- Wired drawer lifecycle in `static/os.js` (`wireHermesDrawer()`, `loadHermesDrawer()`, `openDrawer()`, `closeDrawers()`).

### 5. Static Route Registration
- Updated `hud/routes/static_routes.py` to register `/prototype-4-hermes-stream.html`, `/prototype-5-hermes-matrix.html`, and `/prototype-6-hermes-cockpit.html` under the `static-prototype` service.

---

## Testing Decisions

### 1. Seams Tested
- **UI & Routing Seam**: Highest seam testing through `hud/routes/static_routes.py` verifying that all 6 prototypes are registered, accessible, and return HTTP 200 with correct MIME types.
- **Strict CSP Asset Seam**: Validated via `tests/test_os_dashboard.py` asserting:
  - Zero inline `<script>` tags without `src`.
  - Zero inline `<style>` blocks.
  - Zero inline event handlers (`onclick`, `onsubmit`, etc.).
  - Zero inline `style=` attributes.
- **Data & Telemetry Seam**: Validated via `tests/test_omnibus_peer_review.py` asserting clean execution across all 4 canonical action roles (`ask_jev`, `jev_file_read`, `bash_tool`, `composite_score`, `confidence_gate`).

### 2. Prior Art in the Codebase
- `tests/test_os_dashboard.py`: Existing test suite validating CSP invariants, drawer structures, and board state.
- `tests/test_deep_dispatch_module.py`: Validates route registration and dispatch across static UI assets.
- `tests/test_omnibus_peer_review.py`: Validates Mark-LVI action loading, sandbox execution, and strict string invariants.

---

## Out of Scope

1. **Remote Cloud Model Hosting**: Hermes inference is designed to communicate with the local model daemon on port 8080 or the deterministic `FakeHermesAdapter`. Provisioning remote cloud GPU infrastructure is out of scope.
2. **Replacing Obsidian Vault**: The Obsidian second brain graph remains the authoritative knowledge repository; the visualization cockpit acts as an observer and synchronizer, not a replacement notes editor.
3. **Database Migration to PostgreSQL**: Persistence remains anchored in SQLite via `JobLedger` (ADR-0003); external SQL database migration is not part of this specification.

---

## Further Notes

- All prototypes are fully functional standalone when opened directly via `file://` in a browser or served over HTTP from `hud_server.py`.
- The prototype switcher ribbon links seamlessly between all six iterations, demonstrating the design evolution from Tactical Ring (I), Spatial 3D (II), Dual Cockpit (III), Live Stream (IV), Topology DAG (V), to Unified Efficacy Cockpit (VI).
