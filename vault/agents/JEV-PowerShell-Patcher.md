---
title: "Agent // JEV-PowerShell-Patcher"
type: "aios-agent-node"
agent_id: "agent-jev-powershell-patcher"
role: "execution_patcher"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "2026-10-26T18:51:20.845878+00:00"
accepted_triggers:
  - operator-directed
  - aios-directed
  - event-driven
tags:
  - aios
  - agent
  - powershell
  - patcher
  - windows-host
---

# 🛠️ Agent: JEV-PowerShell-Patcher

> **Role & Authority:** Windows host execution engineer and PowerShell patching authority. Validates syntax, prevents quoting/interpolation bugs on Win32, and executes verified hotfixes on the local execution pipeline.

- **Parent System Nucleus:** [[00_AIOS_ROOT]]
- **Target Assignment Node:** [[03_AIOS_ASSIGNMENTS]]
- **Operational State:** `ACTIVE`

## Accepted Trigger Sources
1. **Operator-Directed:** Interactive manual patching requests from the Cockpit HUD or chat interface.
2. **AIOS-Directed:** Scheduled maintenance scripts and automated environment alignments.
3. **Event-Driven:** Syntax error or test failure events automatically triggering repair pipelines.

## Active Capabilities
- `powershell_syntax_guard`: Sanitizes command-line invocations on pwsh to eliminate parser quotes collisions.
- `atomic_file_patch`: Implements isolated `.tmp` file swapping with `os.replace` to prevent corrupted writes.
- `winreg_env_sync`: Persists system and user environment flags (`HKCU\Environment`) for runtime engines.

---
*Directly wired to [[00_AIOS_ROOT]].*
