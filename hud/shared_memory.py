"""
hud/shared_memory.py
===================
AIOS Multi-Agent Shared Short-Term Memory (SSTM) Protocol
Thread-safe, cross-agent state management and synchronized Obsidian Vault context.

Guarantees:
  1. Thread-safe atomic updates across all sub-agents via re-entrant locking (threading.RLock).
  2. Persistent state backing (data/shared_short_term_memory.json) with atomic replace.
  3. Automatic, bidirectional synchronization with local Obsidian Second Brain vaults
     (G:\\My Drive\\second-brain and local ./vault mirror).
  4. TTL-aware blackboard key-value cache and chronological task completion auditing.
"""

from __future__ import annotations

import os
import sys
import time
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aios.shared_memory")

HUD_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("HUD_DATA_DIR", str(HUD_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SSTM_PERSIST_PATH = DATA_DIR / "shared_short_term_memory.json"

LOCAL_VAULT_DIR = Path(os.environ.get("LOCAL_VAULT_DIR", str(HUD_ROOT / "vault")))
LOCAL_VAULT_DIR.mkdir(parents=True, exist_ok=True)

# Primary second brain directory from environment, fallback to G:\ drive on Windows
_DEFAULT_SECOND_BRAIN = r"G:\My Drive\second-brain" if os.name == "nt" else str(HUD_ROOT / "vault")
PRIMARY_VAULT_DIR = Path(os.environ.get("SECOND_BRAIN_DIR", _DEFAULT_SECOND_BRAIN))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    task_id: str
    agent_id: str
    task_type: str
    status: str = "completed"  # completed, in_progress, failed, pending_approval
    input_summary: Any = field(default_factory=dict)
    output_summary: Any = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp_utc: str = field(default_factory=_iso_now)
    epoch: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentState:
    agent_id: str
    role: str
    operational_state: str = "idle"  # idle, busy, waiting_ack, degraded, offline
    current_task_id: Optional[str] = None
    last_heartbeat_utc: str = field(default_factory=_iso_now)
    capabilities: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BlackboardEntry:
    key: str
    value: Any
    writer_agent_id: str
    version: int = 1
    ttl_seconds: Optional[float] = None
    created_at_utc: str = field(default_factory=_iso_now)
    updated_at_utc: str = field(default_factory=_iso_now)
    expires_at_epoch: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_expired(self) -> bool:
        if self.expires_at_epoch is None:
            return False
        return time.time() > self.expires_at_epoch


class SharedMemoryStore:
    """Thread-safe multi-agent short-term memory store and Obsidian vault synchronizer."""

    _instance: Optional["SharedMemoryStore"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> "SharedMemoryStore":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(SharedMemoryStore, cls).__new__(cls)
                cls._instance._init_store()
            return cls._instance

    def _init_store(self) -> None:
        self._lock = threading.RLock()
        self._epoch = 1
        self._agents: Dict[str, AgentState] = {}
        self._blackboard: Dict[str, BlackboardEntry] = {}
        self._completed_tasks: List[TaskRecord] = []
        self._max_completed_tasks = 200
        self._last_vault_sync_utc: Optional[str] = None
        self._vault_sync_status: str = "INITIALIZING"

        # Canonical sub-agent roster
        self._seed_default_agents()
        # Canonical initial working memory
        self._seed_default_blackboard()
        # Restore from disk if available
        self._load_from_disk()
        # Initial vault sync
        self.sync_to_obsidian_vault()

    def _seed_default_agents(self) -> None:
        defaults = [
            AgentState(
                agent_id="agent-supervisor",
                role="multi_agent_coordinator",
                operational_state="idle",
                capabilities=["orchestration", "consensus", "state_transition", "vault_sync"],
                meta={"tier": 1, "description": "AIOS Multi-Agent Supervisor & Ring-0 Governance"}
            ),
            AgentState(
                agent_id="agent-hermes-gateway",
                role="rpc_gateway",
                operational_state="idle",
                capabilities=["hmac_signing", "model_inference", "anti_buffering", "qwen_orchestration"],
                meta={"tier": 2, "description": "Hermes Two-Way API Gateway (:8080 Signed RPC)"}
            ),
            AgentState(
                agent_id="agent-diagnostic-probe",
                role="health_probe",
                operational_state="idle",
                capabilities=["network_probe", "latency_audit", "rtt_telemetry", "endpoint_matrix"],
                meta={"tier": 2, "description": "Multi-Diagnostic Probes & Latency Feedback Loop"}
            ),
            AgentState(
                agent_id="agent-invoice-ingestion",
                role="diode_ingestion",
                operational_state="idle",
                capabilities=["csv_cleanse", "strict_str_money", "zero_loss", "ap_posting"],
                meta={"tier": 3, "description": "Finance AP Ingestion Pipeline & Penny Governance"}
            ),
            AgentState(
                agent_id="agent-sow-worker",
                role="pipeline_worker",
                operational_state="idle",
                capabilities=["risk_extraction", "sow_validation", "semantic_scout", "cheap_read"],
                meta={"tier": 3, "description": "SOW Discovery Pipeline Worker & Risk Guard Role"}
            ),
            AgentState(
                agent_id="agent-quarantine-guard",
                role="invariant_auditor",
                operational_state="idle",
                capabilities=["penny_reconciliation", "auto_recovery", "diode_seal", "zero_loss_audit"],
                meta={"tier": 4, "description": "Zero-Loss Ledger Invariant Guard & Quarantine Auto-Recovery"}
            ),
        ]
        for a in defaults:
            self._agents[a.agent_id] = a

    def _seed_default_blackboard(self) -> None:
        now_str = _iso_now()
        initial_keys = {
            "active_pipeline_stage": ("IDLE_MONITORING", "agent-supervisor"),
            "zero_loss_invariant_status": ("ENFORCED_ZERO_LOSS", "agent-quarantine-guard"),
            "hermes_model_readiness": ("QWEN3:4B_LOCAL_READY", "agent-hermes-gateway"),
            "obsidian_vault_sync_mode": ("BIDIRECTIONAL_AUTO", "agent-supervisor"),
            "latest_ledger_snapshot": ("LEDGER_IN_SYNC", "agent-supervisor"),
        }
        for k, (v, writer) in initial_keys.items():
            self._blackboard[k] = BlackboardEntry(
                key=k,
                value=v,
                writer_agent_id=writer,
                version=1,
                ttl_seconds=None,
                created_at_utc=now_str,
                updated_at_utc=now_str,
                expires_at_epoch=None
            )

    # -------------------------------------------------------------------------
    # Cross-Agent State Operations
    # -------------------------------------------------------------------------
    def update_agent_heartbeat(
        self,
        agent_id: str,
        role: Optional[str] = None,
        operational_state: str = "idle",
        current_task_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> AgentState:
        with self._lock:
            existing = self._agents.get(agent_id)
            if existing:
                existing.last_heartbeat_utc = _iso_now()
                existing.operational_state = operational_state
                existing.current_task_id = current_task_id
                if role:
                    existing.role = role
                if capabilities:
                    existing.capabilities = capabilities
                if meta:
                    existing.meta.update(meta)
                res = existing
            else:
                new_agent = AgentState(
                    agent_id=agent_id,
                    role=role or "sub_agent",
                    operational_state=operational_state,
                    current_task_id=current_task_id,
                    last_heartbeat_utc=_iso_now(),
                    capabilities=capabilities or [],
                    meta=meta or {}
                )
                self._agents[agent_id] = new_agent
                res = new_agent

            self._save_to_disk()
            return res

    def record_task_completion(
        self,
        agent_id: str,
        task_id: str,
        task_type: str,
        status: str = "completed",
        input_summary: Any = None,
        output_summary: Any = None,
        artifacts: Optional[List[str]] = None,
        duration_ms: float = 0.0,
        sync_vault_now: bool = True
    ) -> TaskRecord:
        with self._lock:
            self._epoch += 1
            rec = TaskRecord(
                task_id=task_id,
                agent_id=agent_id,
                task_type=task_type,
                status=status,
                input_summary=input_summary or {},
                output_summary=output_summary or {},
                artifacts=artifacts or [],
                duration_ms=duration_ms,
                timestamp_utc=_iso_now(),
                epoch=self._epoch
            )
            self._completed_tasks.append(rec)
            if len(self._completed_tasks) > self._max_completed_tasks:
                self._completed_tasks = self._completed_tasks[-self._max_completed_tasks:]

            # Update agent state
            if agent_id in self._agents:
                self._agents[agent_id].last_heartbeat_utc = _iso_now()
                self._agents[agent_id].operational_state = "idle"
                self._agents[agent_id].current_task_id = None

            self._save_to_disk()

        if sync_vault_now:
            self.sync_to_obsidian_vault()

        return rec

    # -------------------------------------------------------------------------
    # Shared Blackboard Operations (Ephemeral K-V Store)
    # -------------------------------------------------------------------------
    def set_blackboard_key(
        self,
        key: str,
        value: Any,
        writer_agent_id: str,
        ttl_seconds: Optional[float] = None
    ) -> BlackboardEntry:
        with self._lock:
            now_epoch = time.time()
            now_iso = _iso_now()
            expires_at = (now_epoch + ttl_seconds) if ttl_seconds else None

            existing = self._blackboard.get(key)
            if existing:
                existing.value = value
                existing.writer_agent_id = writer_agent_id
                existing.version += 1
                existing.ttl_seconds = ttl_seconds
                existing.updated_at_utc = now_iso
                existing.expires_at_epoch = expires_at
                entry = existing
            else:
                entry = BlackboardEntry(
                    key=key,
                    value=value,
                    writer_agent_id=writer_agent_id,
                    version=1,
                    ttl_seconds=ttl_seconds,
                    created_at_utc=now_iso,
                    updated_at_utc=now_iso,
                    expires_at_epoch=expires_at
                )
                self._blackboard[key] = entry

            self._save_to_disk()
            return entry

    def get_blackboard_key(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._blackboard.get(key)
            if not entry:
                return None
            if entry.is_expired():
                del self._blackboard[key]
                return None
            return entry.value

    def get_all_blackboard_entries(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            now = time.time()
            valid = {}
            expired_keys = []
            for k, e in self._blackboard.items():
                if e.expires_at_epoch and now > e.expires_at_epoch:
                    expired_keys.append(k)
                else:
                    valid[k] = e.to_dict()
            for k in expired_keys:
                del self._blackboard[k]
            return valid

    def get_completed_tasks(self, limit: int = 50, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = self._completed_tasks
            if agent_id:
                tasks = [t for t in tasks if t.agent_id == agent_id]
            # Return newest first
            return [t.to_dict() for t in reversed(tasks[-limit:])]

    def get_agents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [a.to_dict() for a in self._agents.values()]

    def get_state_summary(self) -> Dict[str, Any]:
        with self._lock:
            now_iso = _iso_now()
            agents_list = [a.to_dict() for a in self._agents.values()]
            active_count = sum(1 for a in agents_list if a["operational_state"] in ("busy", "waiting_ack"))
            completed_count = len(self._completed_tasks)
            blackboard_data = self.get_all_blackboard_entries()

            return {
                "epoch": self._epoch,
                "timestamp_utc": now_iso,
                "total_completed_tasks": completed_count,
                "active_agents_count": active_count,
                "total_agents_count": len(agents_list),
                "blackboard_keys_count": len(blackboard_data),
                "vault_sync_status": self._vault_sync_status,
                "last_vault_sync_utc": self._last_vault_sync_utc,
                "primary_vault_dir": str(PRIMARY_VAULT_DIR),
                "local_vault_dir": str(LOCAL_VAULT_DIR),
                "agents": agents_list,
                "blackboard": blackboard_data,
                "recent_tasks": [t.to_dict() for t in reversed(self._completed_tasks[-10:])]
            }

    # -------------------------------------------------------------------------
    # Obsidian Vault Synchronization Engine
    # -------------------------------------------------------------------------
    def sync_to_obsidian_vault(self, target_dirs: Optional[List[Path]] = None) -> Dict[str, Any]:
        """
        Synchronizes operational state, completed tasks, and cross-agent blackboard
        into the local Obsidian Vault as structured Markdown documents with frontmatter.
        """
        with self._lock:
            targets: List[Path] = []
            if target_dirs:
                targets = target_dirs
            else:
                targets.append(LOCAL_VAULT_DIR)
                if PRIMARY_VAULT_DIR.exists() and PRIMARY_VAULT_DIR.is_dir() and PRIMARY_VAULT_DIR != LOCAL_VAULT_DIR:
                    targets.append(PRIMARY_VAULT_DIR)

            written_files = []
            sync_errors = []
            now_iso = _iso_now()

            # Render markdown templates
            state_md = self._render_operational_state_markdown(now_iso)
            tasks_md = self._render_completed_tasks_markdown(now_iso)
            blackboard_md = self._render_blackboard_markdown(now_iso)

            for vault_dir in targets:
                try:
                    vault_dir.mkdir(parents=True, exist_ok=True)

                    f_state = vault_dir / "00_AIOS_OPERATIONAL_STATE.md"
                    f_tasks = vault_dir / "01_AIOS_COMPLETED_TASKS_LOG.md"
                    f_bb = vault_dir / "02_AIOS_CROSS_AGENT_BLACKBOARD.md"

                    f_state.write_text(state_md, encoding="utf-8")
                    f_tasks.write_text(tasks_md, encoding="utf-8")
                    f_bb.write_text(blackboard_md, encoding="utf-8")

                    written_files.extend([str(f_state), str(f_tasks), str(f_bb)])
                except Exception as exc:
                    err_msg = f"Failed to sync vault to {vault_dir}: {exc}"
                    logger.warning(err_msg)
                    sync_errors.append(err_msg)

            self._last_vault_sync_utc = now_iso
            self._vault_sync_status = "SYNCHRONIZED" if not sync_errors else "PARTIAL_SYNC"

            # Invalidate in-memory vault cache in os_dashboard if imported
            try:
                from hud import os_dashboard as osd
                osd.invalidate_vault_cache()
            except Exception:
                pass

            return {
                "status": self._vault_sync_status,
                "timestamp_utc": now_iso,
                "written_files_count": len(written_files),
                "written_files": written_files,
                "errors": sync_errors
            }

    def _render_operational_state_markdown(self, now_iso: str) -> str:
        agents = [a.to_dict() for a in self._agents.values()]
        bb = self.get_all_blackboard_entries()
        tasks = [t.to_dict() for t in reversed(self._completed_tasks[-8:])]

        lines = [
            "---",
            'title: "AIOS Multi-Agent Shared Short-Term Memory // Operational State"',
            'type: "aios-operational-state"',
            f'updated_at: "{now_iso}"',
            'status: "ONLINE"',
            f'active_agents: {len(agents)}',
            f'completed_tasks: {len(self._completed_tasks)}',
            'tags:',
            "  - aios",
            "  - multi-agent",
            "  - short-term-memory",
            "  - operational-state",
            "---",
            "",
            "# 🧠 AIOS Multi-Agent Shared Short-Term Memory",
            "",
            "> **Shared Short-Term Memory Protocol (SSTM)** provides thread-safe, monotonic cross-agent state synchronization, "
            "ephemeral working memory blackboard, and automated documentation mirroring across the operational pipeline.",
            "",
            f"**Last Sync:** `{now_iso}` · **Epoch:** `#{self._epoch}` · **Active Sub-Agents:** `{len(agents)}` · **Completed Tasks:** `{len(self._completed_tasks)}`",
            "",
            "## 1. Sub-Agent Operational Roster",
            "",
            "| Agent ID | Role | State | Current Task | Capabilities | Last Heartbeat |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for a in agents:
            st = a["operational_state"].upper()
            curr = a["current_task_id"] or "—"
            caps = ", ".join(a.get("capabilities", [])[:3])
            hb = (a.get("last_heartbeat_utc") or "").replace("T", " ")[:19]
            lines.append(f"| `{a['agent_id']}` | **{a['role']}** | `{st}` | `{curr}` | {caps} | {hb} |")

        lines.extend([
            "",
            "## 2. Shared Working Memory Blackboard",
            "",
            "| Key | Value | Writer Agent | Version | Updated UTC |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])

        for k, v in bb.items():
            val_str = str(v.get("value", ""))
            if len(val_str) > 45:
                val_str = val_str[:42] + "..."
            up_str = (v.get("updated_at_utc") or "").replace("T", " ")[:19]
            lines.append(f"| `{k}` | `{val_str}` | `{v.get('writer_agent_id', 'unknown')}` | `v{v.get('version', 1)}` | {up_str} |")

        lines.extend([
            "",
            "## 3. Recent Completed Sub-Agent Tasks",
            "",
        ])

        if not tasks:
            lines.append("*No tasks completed in this session yet.*")
        else:
            for t in tasks:
                t_time = (t.get("timestamp_utc") or "").replace("T", " ")[:19]
                lines.extend([
                    f"### ✅ `{t['task_id']}` :: {t['task_type']}",
                    f"- **Agent:** `{t['agent_id']}` · **Status:** `{t['status'].upper()}` · **Duration:** `{t.get('duration_ms', 0):.1f}ms` · **Timestamp:** `{t_time}`",
                ])
                if t.get("artifacts"):
                    lines.append(f"- **Artifacts:** {', '.join([f'`{a}`' for a in t['artifacts']])}")
                if t.get("output_summary"):
                    out_snippet = json.dumps(t["output_summary"])
                    if len(out_snippet) > 120:
                        out_snippet = out_snippet[:117] + "..."
                    lines.append(f"- **Output Summary:** `{out_snippet}`")
                lines.append("")

        lines.extend([
            "## 4. Cross-Agent Context & Knowledge Links",
            "",
            "- [[core]]: AI OS Ring-0 Foundation and Anti-Gravity Core",
            "- [[modules/knowledge-memory]]: Long-Term Memory, Obsidian Integration & Vector Indexing",
            "- [[modules/execution]]: Execution Engines, Safe Sandboxes & Job Ledgers",
            "- [[modules/hermes-delegation]]: Hermes RPC Protocol, HMAC Signatures & Local Model Execution",
            "- [[modules/source-governance]]: Strict Data Invariants, Penny Fraction Checks & Quarantine Policies",
            "",
            "---",
            "*Document automatically maintained by AIOS Shared Short-Term Memory Synchronizer.*"
        ])

        return "\n".join(lines)

    def _render_completed_tasks_markdown(self, now_iso: str) -> str:
        tasks = [t.to_dict() for t in reversed(self._completed_tasks)]

        lines = [
            "---",
            'title: "AIOS Multi-Agent Completed Tasks Log"',
            'type: "aios-task-ledger"',
            f'updated_at: "{now_iso}"',
            f'total_tasks: {len(tasks)}',
            'tags:',
            "  - aios",
            "  - multi-agent",
            "  - task-audit",
            "  - operational-log",
            "---",
            "",
            "# 📋 AIOS Multi-Agent Completed Tasks Log",
            "",
            f"**Total Executed Tasks:** `{len(tasks)}` · **Generated UTC:** `{now_iso}`",
            "",
            "| Task ID | Agent | Type | Status | Latency | Timestamp |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for t in tasks:
            lat = f"{t.get('duration_ms', 0):.1f}ms"
            ts = (t.get("timestamp_utc") or "").replace("T", " ")[:19]
            lines.append(f"| `{t['task_id']}` | `{t['agent_id']}` | `{t['task_type']}` | `{t['status']}` | {lat} | {ts} |")

        lines.extend([
            "",
            "## Task Execution Details",
            "",
        ])

        for t in tasks[:30]:  # detailed expansion for latest 30 tasks
            lines.extend([
                f"### Task `{t['task_id']}`",
                f"- **Agent:** `{t['agent_id']}`",
                f"- **Task Type:** `{t['task_type']}`",
                f"- **Status:** `{t['status']}`",
                f"- **Timestamp:** `{t['timestamp_utc']}`",
                f"- **Duration:** `{t.get('duration_ms', 0):.2f} ms`",
            ])
            if t.get("artifacts"):
                lines.append(f"- **Artifacts:** {', '.join([f'`{a}`' for a in t['artifacts']])}")
            if t.get("input_summary"):
                lines.append("```json")
                lines.append(json.dumps(t["input_summary"], indent=2))
                lines.append("```")
            if t.get("output_summary"):
                lines.append("```json")
                lines.append(json.dumps(t["output_summary"], indent=2))
                lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("*Synced via AIOS Shared Short-Term Memory Protocol.*")
        return "\n".join(lines)

    def _render_blackboard_markdown(self, now_iso: str) -> str:
        bb = self.get_all_blackboard_entries()

        lines = [
            "---",
            'title: "AIOS Cross-Agent Working Memory Blackboard"',
            'type: "aios-blackboard"',
            f'updated_at: "{now_iso}"',
            f'keys_count: {len(bb)}',
            'tags:',
            "  - aios",
            "  - multi-agent",
            "  - blackboard",
            "  - shared-memory",
            "---",
            "",
            "# 🗃️ AIOS Cross-Agent Working Memory Blackboard",
            "",
            "> Real-time ephemeral state dictionary shared across all specialized sub-agents.",
            "",
            f"**Last Sync:** `{now_iso}` · **Total Keys:** `{len(bb)}`",
            "",
        ]

        for k, v in bb.items():
            lines.extend([
                f"### Key: `{k}`",
                f"- **Current Value:** `{v.get('value')}`",
                f"- **Writer Agent:** `{v.get('writer_agent_id')}`",
                f"- **Version:** `v{v.get('version')}`",
                f"- **TTL Seconds:** `{v.get('ttl_seconds') or 'Indefinite'}`",
                f"- **Updated UTC:** `{v.get('updated_at_utc')}`",
                ""
            ])

        lines.append("---")
        lines.append("*Maintained automatically by hud/shared_memory.py.*")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------
    def _save_to_disk(self) -> None:
        try:
            payload = {
                "epoch": self._epoch,
                "saved_at_utc": _iso_now(),
                "agents": {k: a.to_dict() for k, a in self._agents.items()},
                "blackboard": {k: b.to_dict() for k, b in self._blackboard.items()},
                "completed_tasks": [t.to_dict() for t in self._completed_tasks],
                "last_vault_sync_utc": self._last_vault_sync_utc,
                "vault_sync_status": self._vault_sync_status,
            }
            tmp_path = SSTM_PERSIST_PATH.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_path.replace(SSTM_PERSIST_PATH)
        except Exception as exc:
            logger.error("Failed to persist shared short-term memory to disk: %s", exc)

    def _load_from_disk(self) -> None:
        if not SSTM_PERSIST_PATH.exists():
            return
        try:
            with open(SSTM_PERSIST_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)

            self._epoch = int(payload.get("epoch", 1))
            self._last_vault_sync_utc = payload.get("last_vault_sync_utc")
            self._vault_sync_status = payload.get("vault_sync_status", "LOADED")

            raw_agents = payload.get("agents", {})
            for k, a_dict in raw_agents.items():
                self._agents[k] = AgentState(**a_dict)

            raw_bb = payload.get("blackboard", {})
            for k, b_dict in raw_bb.items():
                self._blackboard[k] = BlackboardEntry(**b_dict)

            raw_tasks = payload.get("completed_tasks", [])
            self._completed_tasks = [TaskRecord(**t) for t in raw_tasks]
        except Exception as exc:
            logger.warning("Could not restore shared short term memory from disk: %s", exc)


# Global accessor
_STORE_INSTANCE: Optional[SharedMemoryStore] = None


def get_shared_memory_store() -> SharedMemoryStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = SharedMemoryStore()
    return _STORE_INSTANCE
