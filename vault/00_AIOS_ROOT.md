---
title: "AIOS Root Node // Ring-0 Operating System Core"
type: "aios-root-node"
node_id: "aios-root"
ring: 0
status: "ONLINE"
updated_at: "2026-10-26T18:51:20.845878+00:00"
active_agents_count: 5
ledger_jobs_total: 24
ledger_jobs_completed: 24
kanban_board_revision: 50
tags:
  - aios
  - root-node
  - ring-0
  - multi-agent
  - system-core
---

# 🌐 AIOS Root Node (Ring 0 System Core)

> **AIOS Root Architecture**: Primary architectural nucleus providing centralized governance, deterministic agent coordination, and direct bidirectional links across all execution agents, ledger state, and knowledge storage.

**Epoch Synchronization:** `2026-10-26T18:51:20.845878+00:00` · **Architecture:** `Ring-0 AIOS` · **Ledger Status:** `24/24 Jobs Verified`

---

## 1. Direct Agent Wiring (Sub-Agent Roster)

All five active execution agents and daemon services are wired directly to this root node:

```mermaid
graph TD
    ROOT["🌐 AIOS Root Node (Ring 0)"]
    ROOT --> CORE["📘 [[core.md|core.md (Ring 1 Child)]]"]
    ROOT --> AG1["🛠️ [[agents/JEV-PowerShell-Patcher]]"]
    ROOT --> AG2["⏱️ [[agents/cron]]"]
    ROOT --> AG3["🧹 [[agents/maintain-daemon]]"]
    ROOT --> AG4["📡 [[agents/meta-diode-relay]]"]
    ROOT --> AG5["🧠 [[agents/hermes-sub-agents]]"]
    ROOT --> ASSIGN["📋 [[03_AIOS_ASSIGNMENTS]]"]
    ROOT --> STATE["📊 [[00_AIOS_OPERATIONAL_STATE]]"]
```

| Agent Node | Role | Status | Capabilities | Direct Link |
| :--- | :--- | :--- | :--- | :--- |
| **JEV-PowerShell-Patcher** | `execution_patcher` | `ACTIVE` | Script syntax validation, Windows host patcher, execution bridge | [[agents/JEV-PowerShell-Patcher]] |
| **Cron Orchestrator** | `task_scheduler` | `ACTIVE` | Periodic job runner, anti-drift heartbeat, queue dispatcher | [[agents/cron]] |
| **Maintain Daemon** | `maintenance_daemon` | `ACTIVE` | Lockfile purge, zombie PID cleanup, SQLite vacuum, quota audit | [[agents/maintain-daemon]] |
| **Meta-Diode-Relay** | `metadata_diode` | `ACTIVE` | Zero-PII metadata diode, sanitized events, isolated SMTP TLS relay | [[agents/meta-diode-relay]] |
| **Hermes Sub-Agents** | `local_inference_cluster` | `ACTIVE` | VRAM-locked inference (`keep_alive=-1`), HMAC RPC, schema quarantine | [[agents/hermes-sub-agents]] |

---

## 2. Core Routing & Operational Ledgers

- **Assignment Routing Engine:** [[03_AIOS_ASSIGNMENTS]] *(Direct bridge between Kanban orchestrator, SQLite ledger, and educate)*
- **Operational State & Blackboard:** [[00_AIOS_OPERATIONAL_STATE]] *(Thread-safe shared short-term memory & cross-agent blackboard)*
- **Completed Tasks Ledger:** [[01_AIOS_COMPLETED_TASKS_LOG]] *(Monotonic audit log of recent sub-agent executions)*
- **Cross-Agent Blackboard:** [[02_AIOS_CROSS_AGENT_BLACKBOARD]] *(Ephemeral key-value working memory)*
- **Second Brain Base Nucleus (Ring 1 Child):** [[core.md]] *(Taxonomy, module governance, source chronology — demoted to Ring 1 child governed under AIOS Root)*

---

## 3. Live SQLite `job_ledger.db` Metrics

- **Database Path:** `C:\Users\alesh\jev-workspace\delivery-offline\job_ledger.db`
- **Total Ledger Jobs:** `24`
- **Completed:** `24` · **Running:** `0` · **Validated:** `0` · **Approved:** `0` · **Quarantined:** `0`
- **Active Job Types:**
  - `hermes_inference`: 1 job(s)
  - `reconciliation`: 21 job(s)
  - `risk_extraction`: 1 job(s)
  - `sow_discovery_pipeline`: 1 job(s)

### Recent Ledger Audit Entries
| Job ID | Type | State | Scope | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
| `tracer-hermes-1793040509` | `hermes_inference` | `completed` | `hermes-agent` | 2026-10-26T18:48:31 |
| `job-hud-1792263035` | `reconciliation` | `completed` | `hud-operator-scope` | 2026-10-26T16:28:13 |
| `job_sow_1792272864` | `sow_discovery_pipeline` | `completed` | `—` | 2026-10-26T16:28:13 |
| `job-hud-1792967518` | `reconciliation` | `completed` | `hud-operator-scope` | 2026-10-25T22:31:58 |
| `job-hud-1792967215` | `reconciliation` | `completed` | `hud-operator-scope` | 2026-10-25T22:26:55 |

---
*Maintained autonomously by AIOS Obsidian Root Generator.*
