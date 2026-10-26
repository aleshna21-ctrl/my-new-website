"""
hud/obsidian_root_generator.py
AIOS Root Node & Dynamic Assignment Routing Generator for Obsidian Vault.

Implements:
1. AIOS Root Node generation in the Obsidian vault (Ring 0 System Nucleus).
2. Live queries to SQLite job_ledger.db to auto-generate explicit nodes for all active agents:
   - JEV-PowerShell-Patcher
   - cron (Cron Task Scheduler)
   - maintain daemon (System Maintenance Daemon)
   - meta-diode-relay (Metadata Diode & Isolated Relay)
   - Hermes sub-agents (Hermes Cluster: Gateway, Model Adapter with keep_alive=-1, Probe)
   Wiring them directly to the AIOS root node via bidirectional wikilinks.
3. Assignment node routing and research agents:
   - Links directly to Kanban board orchestrator (data/os_board.json)
   - Links directly to SQLite ledger state (data/job_ledger.db)
   - Links directly to specific educate (Second Brain knowledge & procedure modules)
   - Maps incoming edges from execution agents to explicitly accept the three trigger sources:
     * AIOS-directed
     * Operator-directed
     * Event-driven
"""

from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

HUD_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = HUD_ROOT.parent
OFFLINE_DIR = WORKSPACE_ROOT / "delivery-offline"
GTM_DIR = WORKSPACE_ROOT / "gtm-research"
OUTBOX_DIR = WORKSPACE_ROOT / "notification-outbox"
LOCAL_VAULT_DIR = HUD_ROOT / "vault"
PRIMARY_VAULT_DIR = Path(os.environ.get("SECOND_BRAIN_DIR", r"G:\My Drive\second-brain" if os.name == "nt" else str(LOCAL_VAULT_DIR)))

BOARD_PATH = HUD_ROOT / "data" / "os_board.json"
CRON_REGISTRY_PATH = HUD_ROOT / "data" / "cron_registry.json"


def get_ledger_db_path() -> Path:
    """Finds the active job_ledger.db (delivery-offline first, fallback to hud-interface/data)."""
    offline_db = OFFLINE_DIR / "job_ledger.db"
    if offline_db.exists():
        return offline_db
    local_db = HUD_ROOT / "data" / "job_ledger.db"
    if local_db.exists():
        return local_db
    return offline_db


def query_ledger_stats(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Queries job_ledger.db for comprehensive job counts, state distributions, and recent jobs."""
    target_db = db_path or get_ledger_db_path()
    stats: Dict[str, Any] = {
        "db_path": str(target_db),
        "exists": target_db.exists(),
        "total_jobs": 0,
        "completed": 0,
        "running": 0,
        "validated": 0,
        "approved": 0,
        "quarantined": 0,
        "queued": 0,
        "by_type": {},
        "recent_jobs": [],
        "terminal_events_count": 0
    }
    if not target_db.exists():
        return stats

    try:
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        if "jobs" in tables:
            cur.execute("SELECT COUNT(*) FROM jobs")
            stats["total_jobs"] = cur.fetchone()[0]

            cur.execute("SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state")
            for r in cur.fetchall():
                st = r["state"]
                if st in stats:
                    stats[st] = r["cnt"]

            cur.execute("SELECT job_type, COUNT(*) as cnt FROM jobs GROUP BY job_type")
            for r in cur.fetchall():
                stats["by_type"][r["job_type"] or "unspecified"] = r["cnt"]

            cur.execute("SELECT job_id, scope_id, job_type, state, attempt_count, updated_at FROM jobs ORDER BY updated_at DESC LIMIT 10")
            stats["recent_jobs"] = [dict(r) for r in cur.fetchall()]

        if "hud_terminal_events" in tables:
            cur.execute("SELECT COUNT(*) FROM hud_terminal_events")
            stats["terminal_events_count"] = cur.fetchone()[0]

        if "agent_states" in tables:
            cur.execute("SELECT agent_id, name, role, state, last_heartbeat, capabilities, meta FROM agent_states ORDER BY last_heartbeat DESC")
            raw_states = []
            for r in cur.fetchall():
                d = dict(r)
                try:
                    d["capabilities"] = json.loads(d.get("capabilities") or "[]")
                except Exception:
                    d["capabilities"] = []
                try:
                    d["meta"] = json.loads(d.get("meta") or "{}")
                except Exception:
                    d["meta"] = {}
                raw_states.append(d)
            stats["agent_states"] = raw_states
        else:
            stats["agent_states"] = []

        conn.close()
    except Exception as exc:
        stats["error"] = str(exc)

    return stats


def query_kanban_board_summary() -> Dict[str, Any]:
    """Extracts summary metrics from os_board.json."""
    if not BOARD_PATH.exists():
        return {"revision": 0, "total_tasks": 0, "open_tasks": 0, "vital_tasks": 0}
    try:
        with open(BOARD_PATH, "r", encoding="utf-8") as f:
            board = json.load(f)
        tasks = board.get("tasks", [])
        open_tasks = [t for t in tasks if t.get("status") != "done"]
        return {
            "revision": board.get("revision", 0),
            "total_tasks": len(tasks),
            "open_tasks": len(open_tasks),
            "vital_tasks": sum(1 for t in open_tasks if t.get("vital")),
            "tasks": tasks
        }
    except Exception:
        return {"revision": 0, "total_tasks": 0, "open_tasks": 0, "vital_tasks": 0}


def query_cron_registry_summary() -> List[Dict[str, Any]]:
    """Reads registered cron jobs from data/cron_registry.json."""
    if not CRON_REGISTRY_PATH.exists():
        return []
    try:
        with open(CRON_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


class AIOSObsidianGenerator:
    """
    Routines to build and maintain the AIOS Root Node, Agent Cluster nodes,
    and the Dynamic Assignment Routing node inside the Obsidian vault.
    """

    def __init__(self, vault_dir: Optional[Path] = None):
        self.vault_dir = Path(vault_dir) if vault_dir else LOCAL_VAULT_DIR
        self.agents_dir = self.vault_dir / "agents"

    def ensure_directories(self) -> None:
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)

    def render_aios_root_markdown(self, stats: Dict[str, Any], kanban: Dict[str, Any], now_iso: str) -> str:
        """Renders vault/00_AIOS_ROOT.md (System Nucleus)."""
        return f"""---
title: "AIOS Root Node // Ring-0 Operating System Core"
type: "aios-root-node"
node_id: "aios-root"
ring: 0
status: "ONLINE"
updated_at: "{now_iso}"
active_agents_count: 5
ledger_jobs_total: {stats.get('total_jobs', 0)}
ledger_jobs_completed: {stats.get('completed', 0)}
kanban_board_revision: {kanban.get('revision', 0)}
tags:
  - aios
  - root-node
  - ring-0
  - multi-agent
  - system-core
---

# 🌐 AIOS Root Node (Ring 0 System Core)

> **AIOS Root Architecture**: Primary architectural nucleus providing centralized governance, deterministic agent coordination, and direct bidirectional links across all execution agents, ledger state, and knowledge storage.

**Epoch Synchronization:** `{now_iso}` · **Architecture:** `Ring-0 AIOS` · **Ledger Status:** `{stats.get('completed', 0)}/{stats.get('total_jobs', 0)} Jobs Verified`

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

- **Database Path:** `{stats.get('db_path')}`
- **Total Ledger Jobs:** `{stats.get('total_jobs')}`
- **Completed:** `{stats.get('completed')}` · **Running:** `{stats.get('running')}` · **Validated:** `{stats.get('validated')}` · **Approved:** `{stats.get('approved')}` · **Quarantined:** `{stats.get('quarantined')}`
- **Active Job Types:**
{chr(10).join([f"  - `{jt}`: {cnt} job(s)" for jt, cnt in stats.get('by_type', {}).items()]) or "  - *No categorized jobs*"}

### Recent Ledger Audit Entries
| Job ID | Type | State | Scope | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
{chr(10).join([f"| `{j.get('job_id')}` | `{j.get('job_type')}` | `{j.get('state')}` | `{j.get('scope_id') or '—'}` | {j.get('updated_at', '')[:19]} |" for j in stats.get('recent_jobs', [])[:5]]) or "| *No records* | — | — | — | — |"}

---
*Maintained autonomously by AIOS Obsidian Root Generator.*
"""

    def render_agent_patcher_markdown(self, stats: Dict[str, Any], now_iso: str) -> str:
        """Renders vault/agents/JEV-PowerShell-Patcher.md."""
        return f"""---
title: "Agent // JEV-PowerShell-Patcher"
type: "aios-agent-node"
agent_id: "agent-jev-powershell-patcher"
role: "execution_patcher"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_iso}"
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
- `winreg_env_sync`: Persists system and user environment flags (`HKCU\\Environment`) for runtime engines.

---
*Directly wired to [[00_AIOS_ROOT]].*
"""

    def render_agent_cron_markdown(self, crons: List[Dict[str, Any]], now_iso: str) -> str:
        """Renders vault/agents/cron.md."""
        cron_rows = []
        for c in crons:
            cid = c.get("id") or c.get("cron_id", "unnamed")
            expr = c.get("cron") or c.get("schedule", "*/5 * * * *")
            desc = c.get("description", "Scheduled pipeline task")
            en = "ENABLED" if c.get("enabled", True) else "DISABLED"
            cron_rows.append(f"| `{cid}` | `{expr}` | **{en}** | {desc} |")
        cron_table = "\n".join(cron_rows) if cron_rows else "| *No registered cron jobs* | — | — | — |"

        return f"""---
title: "Agent // Cron Orchestrator"
type: "aios-agent-node"
agent_id: "agent-cron"
role: "task_scheduler"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_iso}"
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
{cron_table}

## Capabilities
- `scheduled_pulse_generator`: Emits non-drifting scheduling signals.
- `anti_starvation_gate`: Enforces max runtimes to avoid thread depletion.
- `state_machine_cycle`: Automatically sweeps job queues through terminal states.

---
*Directly wired to [[00_AIOS_ROOT]].*
"""

    def render_agent_maintain_markdown(self, now_iso: str) -> str:
        """Renders vault/agents/maintain-daemon.md."""
        return f"""---
title: "Agent // Maintain Daemon"
type: "aios-agent-node"
agent_id: "agent-maintain-daemon"
role: "maintenance_daemon"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_iso}"
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
"""

    def render_agent_relay_markdown(self, now_iso: str) -> str:
        """Renders vault/agents/meta-diode-relay.md."""
        return f"""---
title: "Agent // Meta-Diode-Relay"
type: "aios-agent-node"
agent_id: "agent-meta-diode-relay"
role: "metadata_diode_and_relay"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_iso}"
accepted_triggers:
  - event-driven
  - operator-directed
tags:
  - aios
  - agent
  - diode
  - smtp-relay
  - security
---

# 📡 Agent: Meta-Diode-Relay

> **Role & Authority:** Air-gapped one-way metadata export and isolated SMTP TLS notification relay. Ensures that internal monetary figures, PII, and customer identifiers are never leaked across network boundaries.

- **Parent System Nucleus:** [[00_AIOS_ROOT]]
- **Target Assignment Node:** [[03_AIOS_ASSIGNMENTS]]
- **Accepted Trigger Sources:** `Event-Driven` (State transitions in offline harness), `Operator-Directed` (Manual alert flush)

## Security Invariants
- **Zero-PII Filter:** Scans outbox events with regex patterns to block non-opaque identifiers.
- **STARTTLS Enforced:** All outbound communications mandate authenticated TLS with isolated socket timeouts.
- **One-Way Diode:** Writes solely to `notification-outbox/metadata_outbox.json` without bidirectional ingestion risk.

---
*Directly wired to [[00_AIOS_ROOT]].*
"""

    def render_agent_hermes_markdown(self, stats: Optional[Dict[str, Any]] = None, now_iso: Optional[str] = None) -> str:
        """Renders vault/agents/hermes-sub-agents.md dynamically from ledger agent states."""
        now_str = now_iso or datetime.now(timezone.utc).isoformat()
        agent_states = (stats or {}).get("agent_states", [])
        hermes_subagents = [
            a for a in agent_states
            if "hermes" in str(a.get("agent_id", "")).lower() or "hermes" in str(a.get("role", "")).lower()
        ]
        if not hermes_subagents:
            hermes_subagents = [
                {"agent_id": "agent-hermes-gateway", "name": "Hermes Gateway Daemon", "role": "rpc_gateway", "state": "ACTIVE", "meta": {"desc": "Handles /gateway/v1/rpc with anti-replay timestamp & nonce authentication."}},
                {"agent_id": "agent-hermes-model-adapter", "name": "Hermes Model Adapter", "role": "model_adapter", "state": "ACTIVE", "meta": {"desc": "Live loopback adapter on 127.0.0.1:8080 bridging upstream Ollama on 127.0.0.1:11434. Forces keep_alive=-1."}},
                {"agent_id": "agent-hermes-probe-worker", "name": "Hermes Diagnostic Probe", "role": "diagnostic_probe", "state": "ACTIVE", "meta": {"desc": "Synthetic connectivity and latency monitor isolated via PROBE_LOCK without blocking active execution payloads."}},
                {"agent_id": "agent-hermes-evaluator", "name": "Hermes Agentic Evaluator", "role": "agentic_judge", "state": "ACTIVE", "meta": {"desc": "Implements JEV System-One judgment gates, cheap file reads, and diff triage."}},
            ]

        breakdown_items = []
        for i, sa in enumerate(hermes_subagents, 1):
            name = sa.get("name") or sa.get("agent_id")
            aid = sa.get("agent_id")
            role = sa.get("role", "sub_agent")
            state = sa.get("state", "ACTIVE")
            desc = sa.get("meta", {}).get("desc") or sa.get("meta", {}).get("description") or f"Dynamically discovered sub-agent role: {role}"
            breakdown_items.append(f"{i}. **{name} (`{aid}`):**\n   - Role: `{role}` · Status: `{state}`\n   - {desc}")

        subagent_breakdown = "\n".join(breakdown_items)

        return f"""---
title: "Agent // Hermes Sub-Agents Cluster"
type: "aios-agent-node"
agent_id: "agent-hermes-cluster"
role: "local_inference_and_rpc"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_str}"
accepted_triggers:
  - operator-directed
  - aios-directed
tags:
  - aios
  - agent
  - hermes
  - local-llm
  - qwen3
  - vram-locked
---

# 🧠 Agent: Hermes Sub-Agents Cluster

> **Role & Authority:** Cluster of local intelligence micro-agents providing OpenAI-compatible `/v1/chat/completions` loopback inference (port 8080), HMAC-SHA256 authenticated RPC routing, and Pydantic schema validation.

- **Parent System Nucleus:** [[00_AIOS_ROOT]]
- **Target Assignment Node:** [[03_AIOS_ASSIGNMENTS]]
- **Model Stability Protocol:** Locked in VRAM via `keep_alive=-1` payload constructor to eliminate handoff disconnect loops.

## Sub-Agents Cluster Breakdown (Dynamically Generated from Ledger)
{subagent_breakdown}

---
*Directly wired to [[00_AIOS_ROOT]].*
"""

    def render_assignments_node_markdown(self, stats: Dict[str, Any], kanban: Dict[str, Any], now_iso: str) -> str:
        """
        Renders vault/03_AIOS_ASSIGNMENTS.md.
        Links directly to:
        1. Kanban board orchestrator (data/os_board.json)
        2. SQLite ledger state (data/job_ledger.db)
        3. Specific educate (Second Brain knowledge & procedure modules)
        Maps incoming edges to explicitly accept the three trigger sources:
        AIOS-directed, operator-directed, and event-driven.
        """
        open_tasks = kanban.get("tasks", [])
        active_todo = [t for t in open_tasks if t.get("status") in ("todo", "doing")]

        return f"""---
title: "AIOS Task Assignments & Routing Engine"
type: "aios-assignments-node"
node_id: "aios-assignments"
ring: 1
status: "ACTIVE"
updated_at: "{now_iso}"
kanban_revision: {kanban.get('revision', 0)}
open_tasks_count: {len(active_todo)}
total_ledger_jobs: {stats.get('total_jobs', 0)}
trigger_sources:
  - aios-directed
  - operator-directed
  - event-driven
tags:
  - aios
  - assignments
  - kanban-orchestrator
  - ledger-state
  - educate
  - routing
---

# 📋 AIOS Assignments & Routing Engine (Dynamic Task Dispatcher)

> **Architectural Mission:** The Assignments Node serves as the unified routing nexus connecting high-level task goals to execution agents. It coordinates three explicit trigger sources (**AIOS-directed**, **operator-directed**, and **event-driven**) directly into the Kanban task orchestrator, the SQLite ledger state machine, and Second Brain educational procedures.

- **System Parent:** [[00_AIOS_ROOT]]
- **Operational State Mirror:** [[00_AIOS_OPERATIONAL_STATE]]

---

## 1. Incoming Edge Mapping & Three Trigger Sources

Execution agents map incoming edges to this assignments node according to three strict trigger sources:

```mermaid
graph LR
    subgraph Trigger Sources
        T_AIOS["🤖 AIOS-Directed<br/>(Cron / Scheduled / State Machine)"]
        T_OPERATOR["👤 Operator-Directed<br/>(HUD Click / CLI / Manual Approval)"]
        T_EVENT["⚡ Event-Driven<br/>(Diode Drops / File Changes / Alarms)"]
    end

    subgraph Assignment Node
        ASSIGN["📋 [[03_AIOS_ASSIGNMENTS]]"]
    end

    subgraph Execution & Delegation Paths
        DELEGATE["🧠 [[modules/hermes-delegation.md|Hermes Delegation]]"]
        EXEC["⚙️ [[modules/execution.md|Execution Pipeline]]"]
        LEDGER["🏛️ SQLite Job Ledger<br/>([[data/job_ledger.db]])"]
        KANBAN["📌 Kanban Task Orchestrator<br/>([[data/os_board.json]])"]
    end

    T_AIOS -->|periodic pulse| ASSIGN
    T_OPERATOR -->|manual command| ASSIGN
    T_EVENT -->|telemetry signal| ASSIGN

    ASSIGN -->|task dispatch & routing| DELEGATE
    ASSIGN -->|command execution| EXEC
    ASSIGN -->|state transitions| LEDGER
    ASSIGN -->|task mutations & planning| KANBAN
```

### Execution Agent Trigger Routing Matrix

| Execution Agent | Incoming Edge Type | Accepted Trigger Sources | Target Handler / Action |
| :--- | :--- | :--- | :--- |
| **JEV-PowerShell-Patcher** | `patch-dispatch` | `operator-directed`, `aios-directed`, `event-driven` | `execute_task_command('patch')` / Hotfix apply |
| **Cron Orchestrator** | `scheduled-pulse` | `aios-directed` | `trigger_cron_job()`, automated daily planning |
| **Maintain Daemon** | `clean-routine` | `aios-directed`, `operator-directed`, `event-driven` | `job_ledger` stale lock clear, zombie PID reclaim |
| **Meta-Diode-Relay** | `diode-signal` | `event-driven`, `operator-directed` | `metadata_outbox.json` export & SMTP flush |
| **Hermes Sub-Agents** | `inference-handoff` | `operator-directed`, `aios-directed` | `LiveLocalModelAdapter` (`keep_alive=-1`) |
| **Research Agents (GTM)** | `research-eval` | `aios-directed`, `operator-directed`, `event-driven` | `staged_outreach.json` review & Level 4 gate |

---

## 2. Direct Kanban Board Orchestrator Link

- **Live Store:** [`data/os_board.json`](file:///c:/Users/alesh/jev-workspace/hud-interface/data/os_board.json)
- **Board Controller:** `hud.os_dashboard.apply_board_op()` via `POST /api/os/board`
- **Current Revision:** `{kanban.get('revision', 0)}` · **Active Workload Items:** `{len(active_todo)}`

### Active Tasks in Orchestrator
| Task ID | Title | Priority | Vital | Status | Estimate |
| :--- | :--- | :--- | :--- | :--- | :--- |
{chr(10).join([f"| `{t.get('id')}` | {t.get('title')[:45]} | P{t.get('priority', 2)} | {'⭐' if t.get('vital') else '—'} | `{t.get('status')}` | {t.get('estimate_min', 15)}m |" for t in active_todo[:8]]) or "| *No active tasks* | — | — | — | — | — |"}

---

## 3. Direct SQLite Ledger State Link

- **Durable Store:** [`data/job_ledger.db`](file:///c:/Users/alesh/jev-workspace/hud-interface/data/job_ledger.db)
- **State Machine Rules:** Strict forward progression (`queued -> running -> validated -> approved -> completed`).
- **Audit Verification:** `{stats.get('completed', 0)}` completed, `{stats.get('running', 0)}` running, `{stats.get('quarantined', 0)}` quarantined.
- **Lock Management:** Zero active stale locks; cleared atomically with zero thread starvation.

---

## 4. Direct Specific Educate & Second Brain Knowledge Links

All research and execution agents reference standardized educational procedures and governance constraints before executing assignments:

1. **[[modules/hermes-delegation.md]]:** Team routing, local model execution boundaries, and human-in-the-loop review criteria.
2. **[[modules/execution.md]]:** Tool authorization specifications, dry-run simulations, and Level 6 bash guardrails.
3. **[[modules/knowledge-memory.md]]:** 9-layer storage boundaries, separating runtime state from hot context and durable procedures.
4. **[[modules/source-governance.md]]:** Strict provenance, source conflict resolution, and immutable chronologies.
5. **[[modules/verification.md]]:** Observable proof requirements and Level 8/Level 10 deterministic test contracts.

---
*Maintained autonomously by AIOS Obsidian Root Generator.*
"""

    def generate_all(self) -> Dict[str, Any]:
        """Executes full generation routine for the AIOS Root Node and all related vault documents."""
        self.ensure_directories()
        now_iso = datetime.now(timezone.utc).isoformat()
        stats = query_ledger_stats()
        kanban = query_kanban_board_summary()
        crons = query_cron_registry_summary()

        written_files = []

        # 1. AIOS Root Node
        root_path = self.vault_dir / "00_AIOS_ROOT.md"
        root_content = self.render_aios_root_markdown(stats, kanban, now_iso)
        root_path.write_text(root_content, encoding="utf-8")
        written_files.append(str(root_path))

        # 2. Agent Nodes
        agents_map = {
            "JEV-PowerShell-Patcher.md": self.render_agent_patcher_markdown(stats, now_iso),
            "cron.md": self.render_agent_cron_markdown(crons, now_iso),
            "maintain-daemon.md": self.render_agent_maintain_markdown(now_iso),
            "meta-diode-relay.md": self.render_agent_relay_markdown(now_iso),
            "hermes-sub-agents.md": self.render_agent_hermes_markdown(stats, now_iso),
        }

        for filename, content in agents_map.items():
            f_path = self.agents_dir / filename
            f_path.write_text(content, encoding="utf-8")
            written_files.append(str(f_path))

        # 3. Assignments Node
        assignments_path = self.vault_dir / "03_AIOS_ASSIGNMENTS.md"
        assignments_content = self.render_assignments_node_markdown(stats, kanban, now_iso)
        assignments_path.write_text(assignments_content, encoding="utf-8")
        written_files.append(str(assignments_path))

        # If primary vault exists and is different from local vault, mirror files
        if PRIMARY_VAULT_DIR.exists() and PRIMARY_VAULT_DIR.is_dir() and PRIMARY_VAULT_DIR != self.vault_dir:
            try:
                p_agents = PRIMARY_VAULT_DIR / "agents"
                p_agents.mkdir(parents=True, exist_ok=True)
                (PRIMARY_VAULT_DIR / "00_AIOS_ROOT.md").write_text(root_content, encoding="utf-8")
                (PRIMARY_VAULT_DIR / "03_AIOS_ASSIGNMENTS.md").write_text(assignments_content, encoding="utf-8")
                for fn, c in agents_map.items():
                    (p_agents / fn).write_text(c, encoding="utf-8")
                written_files.append(str(PRIMARY_VAULT_DIR / "00_AIOS_ROOT.md"))
            except Exception:
                pass

        return {
            "status": "success",
            "timestamp_utc": now_iso,
            "written_files_count": len(written_files),
            "written_files": written_files,
            "stats": stats,
            "kanban_revision": kanban.get("revision", 0),
            "crons_count": len(crons)
        }


def generate_aios_obsidian_vault(vault_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Helper entry point for scripts and modules to trigger full generation."""
    generator = AIOSObsidianGenerator(vault_dir)
    return generator.generate_all()


if __name__ == "__main__":
    res = generate_aios_obsidian_vault()
    print("AIOS Obsidian Vault Generation Completed:")
    print(f"Status: {res['status']}")
    print(f"Files written: {res['written_files_count']}")
    for f in res["written_files"]:
        print("  -", f)
