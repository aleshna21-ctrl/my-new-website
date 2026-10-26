---
name: realtime-visualization
description: "Implement and operate real-time dashboard visualizations featuring streaming charts, multi-level hierarchy layouts, and cross-filtered coordinated views. ACTIVATE this skill when rendering live SQLite data streams, DAG hierarchies, or interactive analytical visualizations."
---

# Real-Time Visualization Skill

## Purpose & Architecture
The Real-Time Visualization skill defines the protocols, layout engines, and coordinated interaction patterns used by the HUD server and front-end interface to render live SQLite datasets without polling jitter or frame drops.

```text
+-------------------+      SSE Push (:5050/api/os/stream)      +--------------------+
| SQLite Ledger     | ---------------------------------------> | Streaming Charts   |
| (job_ledger.db)   |                                          | (Time-Series SVG)  |
+-------------------+                                          +--------------------+
        |                                                                ^
        v                                                                |
+-------------------+      Hierarchy Layout API (:5050/...)    +--------------------+
| DAG Generator     | ---------------------------------------> | Coordinated Views  |
| (Tier 1 -> 4)     |                                          | (Cross-Filter Bus) |
+-------------------+                                          +--------------------+
```

## Key Visualization Patterns

### 1. Streaming Time-Series Charts
- **Rolling Window**: Maintains a 60-second circular buffer rendered via SVG path extrapolation (`L`, `C` cubic beziers) or 2D HTML5 canvas.
- **Dual-Axis Synchronization**:
  - Left axis: Credit burn rate and operational latency (ms).
  - Right axis: SQLite job throughput (jobs/sec) and active daemon pulses.
- **Zero-Buffering**: Powered by Server-Sent Events (SSE) with `X-Accel-Buffering: no` for 60fps movement.

### 2. Multi-Level Hierarchy Layout
- **DAG Layout Engine**: Groups nodes by structural layer:
  - **Tier 1 (Root Governance)**: AIOS Core, Mark LVI System, Financial Diode.
  - **Tier 2 (Scope Clusters)**: Client and operator domains (`cambridge-specialty`, `vetpowered-cnc`, `adversarial-batch-01`, etc.).
  - **Tier 3 (SQLite Jobs)**: Discrete jobs from the `jobs` table with current transition status (`queued`, `running`, `validated`, `approved`, `completed`, `quarantined`).
  - **Tier 4 (Terminal Events)**: Durable diode events captured in `hud_terminal_events`.
- **Node Geometry**: Orthogonal and bezier connector routes displaying state flow directions and attempt counts.

### 3. Coordinated Views (Cross-Filtering)
- **Synchronized Interaction**:
  - Selecting a Scope or Job node in the **Hierarchy Layout** immediately filters the **Streaming Chart** time window and highlights matching rows in the **SQLite Data Inspector**.
  - Hovering a time-slice in the **Streaming Chart** pinpoints active jobs in the hierarchy and renders instantaneous credit metrics.
  - Toggling state filters (`completed`, `quarantined`, `running`) simultaneously updates the hierarchy tree and data table.

## Endpoints
- `GET /api/cortex/streaming-series`: Returns time-series metrics array for chart initialization.
- `GET /api/cortex/hierarchy`: Returns structured hierarchy JSON with nodes, links, and node metadata.
- `GET /api/sqlite/ledger`: Returns raw and parsed SQLite table records with schema metadata.
