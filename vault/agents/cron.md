---
title: "Agent // Cron Orchestrator"
type: "aios-agent-node"
agent_id: "agent-cron"
role: "task_scheduler"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "2026-10-26T18:51:20.845878+00:00"
accepted_triggers:
  - aios-directed
tags:
  - aios
  - agent
  - cron
  - scheduler
---

# ⏱️ Agent: Cron Orchestrator

> **Role & Authority:** Autonomous recurring task scheduler and heart-beat generator. Dispatches time-series pulses and hands off jobs to the Kanban task orchestrator without human latency.

- **Parent System Nucleus:** [[00_AIOS_ROOT]]
- **Target Assignment Node:** [[03_AIOS_ASSIGNMENTS]]
- **Primary Trigger Class:** `AIOS-Directed` (Scheduled time pulses)

## Active Scheduled Crons
| Cron ID | Schedule | Status | Description |
| :--- | :--- | :--- | :--- |
| `cron-backup-daily` | `*/5 * * * *` | **ENABLED** | Automated snapshot archive of SQLite ledger, data fixtures, and vault stores at 03:15 UTC. |
| `cron-ledger-invariant` | `*/5 * * * *` | **ENABLED** | Periodic verification of zero-loss financial invariant: Received == Accepted + Quarantined + Duplicates. |
| `cron-hermes-probe` | `*/5 * * * *` | **ENABLED** | Probe 127.0.0.1:8080 model endpoint to verify local Ollama inference pipeline and latency. |
| `cron-gtm-sync` | `*/5 * * * *` | **ENABLED** | Scans staged outreach drafts queue and updates notification diode state. |
| `cron-board-health` | `*/5 * * * *` | **ENABLED** | Evaluates vital tasks overdue dates and updates board schedule buffers. |

## Capabilities
- `scheduled_pulse_generator`: Emits non-drifting scheduling signals.
- `anti_starvation_gate`: Enforces max runtimes to avoid thread depletion.
- `state_machine_cycle`: Automatically sweeps job queues through terminal states.

---
*Directly wired to [[00_AIOS_ROOT]].*
