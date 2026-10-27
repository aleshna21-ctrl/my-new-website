---
title: "Agent // Maintain Daemon"
type: "aios-agent-node"
agent_id: "agent-maintain-daemon"
role: "maintenance_daemon"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "2026-10-27T09:53:57.487287+00:00"
accepted_triggers:
  - aios-directed
  - operator-directed
  - event-driven
tags:
  - aios
  - agent
  - maintenance
  - lock-purge
  - hygiene
---

# 🧹 Agent: Maintain Daemon

> **Role & Authority:** System hygiene and stability maintainer. Cleans stranded sidecar lock files (`.lock`), terminates zombie PIDs, vacuums SQLite storage, and audits disk quotas.

- **Parent System Nucleus:** [[00_AIOS_ROOT]]
- **Target Assignment Node:** [[03_AIOS_ASSIGNMENTS]]
- **Accepted Trigger Sources:** `AIOS-Directed`, `Operator-Directed`, `Event-Driven` (Lock contention timeouts)

## Maintained Targets
- `data/os_board.json.lock`: Automatically unlinked if holding process is deceased.
- `state/server.lock`: Verified on boot to prevent multiple bind collisions.
- `job_ledger.db`: Monitored for uncommitted WAL transactions and stuck locks.

---
*Directly wired to [[00_AIOS_ROOT]].*
