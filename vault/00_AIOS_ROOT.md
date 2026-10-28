---
title: "AIOS Root Node // Ring-0 Operating System Core"
type: "aios-root-node"
node_id: "aios-root"
ring: 0
status: "ONLINE"
updated_at: "2026-10-28T00:42:28.504181+00:00"
active_agents_count: 5
ledger_jobs_total: 76
ledger_jobs_completed: 24
kanban_board_revision: 92
tags:
  - aios
  - root-node
  - ring-0
  - multi-agent
  - system-core
---

# 🌐 AIOS Root Node (Ring 0 System Core)

> **AIOS Root Architecture**: Primary architectural nucleus providing centralized governance, deterministic agent coordination, and direct bidirectional links across all execution agents, ledger state, and knowledge storage.

**Epoch Synchronization:** `2026-10-28T00:42:28.504181+00:00` · **Architecture:** `Ring-0 AIOS` · **Ledger Status:** `24/76 Jobs Verified`

---

## 1. Direct Agent Wiring (Sub-Agent Roster)

All five active execution agents and daemon services are wired directly to this root node:

```mermaid
graph TD
    ROOT["🌐 AIOS Root Node (Ring 0)"]
    ROOT --> CORE["📘 [[core.md|core.md (Ring 1 Child)]]"]
    ROOT --> GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"]
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
- **GTM Outreach & Research Engine:** [[04_AIOS_GTM_OUTREACH]] *(Autonomous B2B pipeline, dedicated client research nodes, Hermes email drafting)*
- **Operational State & Blackboard:** [[00_AIOS_OPERATIONAL_STATE]] *(Thread-safe shared short-term memory & cross-agent blackboard)*
- **Completed Tasks Ledger:** [[01_AIOS_COMPLETED_TASKS_LOG]] *(Monotonic audit log of recent sub-agent executions)*
- **Cross-Agent Blackboard:** [[02_AIOS_CROSS_AGENT_BLACKBOARD]] *(Ephemeral key-value working memory)*
- **Second Brain Base Nucleus (Ring 1 Child):** [[core.md]] *(Taxonomy, module governance, source chronology — demoted to Ring 1 child governed under AIOS Root)*

---

## 3. Live SQLite `job_ledger.db` Metrics

- **Database Path:** `C:\Users\alesh\jev-workspace\delivery-offline\job_ledger.db`
- **Total Ledger Jobs:** `76`
- **Completed:** `24` · **Running:** `0` · **Validated:** `0` · **Approved:** `0` · **Quarantined:** `0`
- **Active Job Types:**
  - `agent_task`: 4 job(s)
  - `architecture_routing_task`: 28 job(s)
  - `chaos_fatal_task`: 15 job(s)
  - `discrepancy_audit`: 1 job(s)
  - `execute_model_triage`: 1 job(s)
  - `hermes_inference`: 1 job(s)
  - `reconcile_ap_ar`: 1 job(s)
  - `reconciliation`: 21 job(s)
  - `reconciliation_triage`: 2 job(s)
  - `risk_extraction`: 1 job(s)
  - `sow_discovery_pipeline`: 1 job(s)

### Recent Ledger Audit Entries
| Job ID | Type | State | Scope | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
| `routing-test-1793148138` | `architecture_routing_task` | `[ DONE ]` | `aios-systems-architect` | 2026-10-28T00:42:22 |
| `routing-test-1793147962` | `architecture_routing_task` | `[ DONE ]` | `aios-systems-architect` | 2026-10-28T00:39:25 |
| `routing-test-1793147575` | `architecture_routing_task` | `[ DONE ]` | `aios-systems-architect` | 2026-10-28T00:32:59 |
| `routing-test-1793115127` | `architecture_routing_task` | `[ DONE ]` | `aios-systems-architect` | 2026-10-27T15:32:11 |
| `routing-test-1793114825` | `architecture_routing_task` | `[ DONE ]` | `aios-systems-architect` | 2026-10-27T15:27:08 |

---
*Maintained autonomously by AIOS Obsidian Root Generator.*
