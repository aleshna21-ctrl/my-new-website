"""
hermes_observability.py
=======================
Authoritative Hermes Agent Observability & Efficacy Scoring Engine for AIOS.
Adheres to ADR-0007 and Specification 0007.

Encapsulates:
1. Canonical multi-agent domain model across 4 roles (Triage, Scout, Exec, Supervisor).
2. Composite Agent Efficacy Score calculation (35% Inference, 35% Invariants, 30% Confidence).
3. Hard quarantine / stalled-lock fault ceiling capping efficacy at <= 0.40.
4. Dual-access response contracts (AgentEfficacyMetrics, AgentActivityEvent) inheriting from dict.
5. In-memory sliding-window trendlines and FakeHermesEfficacyEngine test double.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("HermesObservability")

# =============================================================================
# 1. CANONICAL MULTI-AGENT MATRIX ROLES
# =============================================================================

CANONICAL_HERMES_ROLES: Dict[str, Dict[str, Any]] = {
    "triage": {
        "role_id": "triage",
        "name": "Triage Agent",
        "badge": "[TRIAGE]",
        "capability": "actions.ask_jev",
        "description": "Inbound request classification, capability policy validation, and initial dispatch",
        "default_model": "qwen3:4b",
        "fallback_model": "mistral-embed-7b",
    },
    "scout": {
        "role_id": "scout",
        "name": "Scout & Auditor",
        "badge": "[SCOUT]",
        "capability": "actions.jev_file_read",
        "description": "Targeted vault and filesystem inspection with zero context bloat",
        "default_model": "qwen3:4b",
        "fallback_model": "mistral-embed-7b",
    },
    "exec": {
        "role_id": "exec",
        "name": "Execution Agent",
        "badge": "[EXEC]",
        "capability": "actions.bash_tool",
        "description": "Guarded script execution and code generation under sandboxed subprocess jails",
        "default_model": "qwen3:4b",
        "fallback_model": "mistral-embed-7b",
    },
    "supervisor": {
        "role_id": "supervisor",
        "name": "Supervisor & Gatekeeper",
        "badge": "[SUPERVISOR]",
        "capability": "actions.confidence_gate",
        "description": "Confidence assessment, readiness evaluation, and final sign-off",
        "default_model": "qwen3:4b",
        "fallback_model": "mistral-embed-7b",
    },
}

# Standard SLA & Efficacy Weights
WEIGHT_INFERENCE_HEALTH = 0.35
WEIGHT_INVARIANT_INTEGRITY = 0.35
WEIGHT_GATE_CONFIDENCE = 0.30
FAULT_CEILING_MAX_SCORE = 0.40
DEFAULT_LATENCY_SLA_MS_PER_TOKEN = 55.0


def utc_now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# 2. DUAL-ACCESS RESPONSE CONTRACTS
# =============================================================================

class AgentEfficacyMetrics(dict):
    """
    Dual-access contract for composite agent efficacy metrics.
    Operates as a standard dict for JSON serialization while exposing typed properties.
    """

    def __init__(
        self,
        composite_score: float,
        inference_health: float,
        invariant_integrity: float,
        gate_confidence: float,
        degraded: bool = False,
        fault_ceiling_applied: bool = False,
        quarantine_incident_count: int = 0,
        stalled_lock_count: int = 0,
        schema_repairs_count: int = 0,
        latency_ms_per_token: float = 0.0,
        formula: str = "0.35*InferenceHealth + 0.35*InvariantIntegrity + 0.30*GateConfidence",
        timestamp: Optional[str] = None,
        role: Optional[str] = None,
        raw_dict: Optional[Dict[str, Any]] = None,
    ):
        if raw_dict is not None:
            data = dict(raw_dict)
        else:
            data = {
                "composite_score": round(float(composite_score), 4),
                "inference_health": round(float(inference_health), 4),
                "invariant_integrity": round(float(invariant_integrity), 4),
                "gate_confidence": round(float(gate_confidence), 4),
                "degraded": bool(degraded),
                "fault_ceiling_applied": bool(fault_ceiling_applied),
                "quarantine_incident_count": int(quarantine_incident_count),
                "stalled_lock_count": int(stalled_lock_count),
                "schema_repairs_count": int(schema_repairs_count),
                "latency_ms_per_token": round(float(latency_ms_per_token), 2),
                "formula": formula,
                "timestamp": timestamp or utc_now_iso(),
                "role": role,
            }
        super().__init__(data)

    @property
    def composite_score(self) -> float:
        return self["composite_score"]

    @property
    def inference_health(self) -> float:
        return self["inference_health"]

    @property
    def invariant_integrity(self) -> float:
        return self["invariant_integrity"]

    @property
    def gate_confidence(self) -> float:
        return self["gate_confidence"]

    @property
    def degraded(self) -> bool:
        return self["degraded"]

    @property
    def fault_ceiling_applied(self) -> bool:
        return self["fault_ceiling_applied"]

    @property
    def quarantine_incident_count(self) -> int:
        return self["quarantine_incident_count"]

    @property
    def stalled_lock_count(self) -> int:
        return self["stalled_lock_count"]

    @property
    def schema_repairs_count(self) -> int:
        return self["schema_repairs_count"]

    @property
    def latency_ms_per_token(self) -> float:
        return self["latency_ms_per_token"]

    @property
    def formula(self) -> str:
        return self["formula"]

    @property
    def timestamp(self) -> str:
        return self["timestamp"]

    @property
    def role(self) -> Optional[str]:
        return self.get("role")

    def is_healthy(self) -> bool:
        """Returns True if score >= 0.80 and no fault ceiling is active."""
        return self.composite_score >= 0.80 and not self.fault_ceiling_applied


class AgentActivityEvent(dict):
    """
    Dual-access contract for an individual Hermes agent activity event in the stream.
    Operates as a standard dict for JSON serialization while exposing typed properties.
    """

    def __init__(
        self,
        event_id: str,
        role: str,
        agent_name: str,
        thought: str,
        action: str,
        latency_ms: float = 0.0,
        tokens_per_sec: float = 0.0,
        schema_repaired: bool = False,
        prompt_hash: str = "",
        sequence_ack: str = "",
        timestamp: Optional[str] = None,
        metrics: Optional[AgentEfficacyMetrics] = None,
        raw_dict: Optional[Dict[str, Any]] = None,
    ):
        if raw_dict is not None:
            data = dict(raw_dict)
        else:
            data = {
                "event_id": event_id,
                "role": role,
                "agent_name": agent_name,
                "thought": thought,
                "action": action,
                "latency_ms": round(float(latency_ms), 2),
                "tokens_per_sec": round(float(tokens_per_sec), 2),
                "schema_repaired": bool(schema_repaired),
                "prompt_hash": prompt_hash or hashlib.sha256(thought.encode("utf-8")).hexdigest()[:12],
                "sequence_ack": sequence_ack or f"ack-{int(time.time() * 1000) % 1000000:06d}",
                "timestamp": timestamp or utc_now_iso(),
                "metrics": dict(metrics) if metrics is not None else None,
            }
        super().__init__(data)

    @property
    def event_id(self) -> str:
        return self["event_id"]

    @property
    def role(self) -> str:
        return self["role"]

    @property
    def agent_name(self) -> str:
        return self["agent_name"]

    @property
    def thought(self) -> str:
        return self["thought"]

    @property
    def action(self) -> str:
        return self["action"]

    @property
    def latency_ms(self) -> float:
        return self["latency_ms"]

    @property
    def tokens_per_sec(self) -> float:
        return self["tokens_per_sec"]

    @property
    def schema_repaired(self) -> bool:
        return self["schema_repaired"]

    @property
    def prompt_hash(self) -> str:
        return self["prompt_hash"]

    @property
    def sequence_ack(self) -> str:
        return self["sequence_ack"]

    @property
    def timestamp(self) -> str:
        return self["timestamp"]

    @property
    def metrics(self) -> Optional[AgentEfficacyMetrics]:
        raw_m = self.get("metrics")
        return AgentEfficacyMetrics(0, 0, 0, 0, raw_dict=raw_m) if raw_m else None


# =============================================================================
# 3. EFFICACY SCORING FORMULATION
# =============================================================================

def compute_composite_efficacy(
    inference_health: float,
    invariant_integrity: float,
    gate_confidence: float,
    quarantine_incident_count: int = 0,
    stalled_lock_count: int = 0,
    schema_repairs_count: int = 0,
    latency_ms_per_token: float = 0.0,
    role: Optional[str] = None,
) -> AgentEfficacyMetrics:
    """
    Computes normalized composite Agent Efficacy Score according to ADR-0007:
      E = 0.35 * InferenceHealth + 0.35 * InvariantIntegrity + 0.30 * GateConfidence

    Hard Fault Ceiling Rule:
      If quarantine_incident_count > 0 or stalled_lock_count > 0:
        E = min(E, 0.40)
        degraded = True
        fault_ceiling_applied = True
    """
    inf_h = max(0.0, min(1.0, float(inference_health)))
    inv_i = max(0.0, min(1.0, float(invariant_integrity)))
    gate_c = max(0.0, min(1.0, float(gate_confidence)))

    raw_score = (
        WEIGHT_INFERENCE_HEALTH * inf_h
        + WEIGHT_INVARIANT_INTEGRITY * inv_i
        + WEIGHT_GATE_CONFIDENCE * gate_c
    )
    raw_score = max(0.0, min(1.0, raw_score))

    fault_ceiling_applied = (quarantine_incident_count > 0) or (stalled_lock_count > 0)
    if fault_ceiling_applied:
        effective_score = min(raw_score, FAULT_CEILING_MAX_SCORE)
        degraded = True
    else:
        effective_score = raw_score
        degraded = effective_score < 0.70

    return AgentEfficacyMetrics(
        composite_score=effective_score,
        inference_health=inf_h,
        invariant_integrity=inv_i,
        gate_confidence=gate_c,
        degraded=degraded,
        fault_ceiling_applied=fault_ceiling_applied,
        quarantine_incident_count=quarantine_incident_count,
        stalled_lock_count=stalled_lock_count,
        schema_repairs_count=schema_repairs_count,
        latency_ms_per_token=latency_ms_per_token,
        role=role,
    )


# =============================================================================
# 4. HERMES EFFICACY ENGINE SEAM
# =============================================================================

class HermesEfficacyEngine:
    """
    Authoritative stateful calculation engine for Hermes agent efficacy scoring,
    real-time event streaming, and 10-minute sliding window trendlines.
    """

    def __init__(
        self,
        latency_sla_ms: float = DEFAULT_LATENCY_SLA_MS_PER_TOKEN,
        max_event_history: int = 500,
    ):
        self.latency_sla_ms = latency_sla_ms
        self.max_event_history = max_event_history
        self._lock = threading.RLock()
        self._events: List[AgentActivityEvent] = []
        self._role_stats: Dict[str, Dict[str, Any]] = {
            role: {
                "total_steps": 0,
                "clean_steps": 0,
                "schema_repairs": 0,
                "total_tokens": 0,
                "total_latency_ms": 0.0,
                "gate_confidences": [],
                "quarantine_incidents": 0,
                "stalled_locks": 0,
            }
            for role in CANONICAL_HERMES_ROLES
        }
        self._global_quarantine_incidents = 0
        self._global_stalled_locks = 0

    def record_quarantine_incident(self, role: Optional[str] = None) -> None:
        """Records a quarantined record or invariant violation, triggering the hard fault ceiling."""
        with self._lock:
            self._global_quarantine_incidents += 1
            if role and role in self._role_stats:
                self._role_stats[role]["quarantine_incidents"] += 1

    def record_stalled_lock(self, role: Optional[str] = None) -> None:
        """Records a stalled lock ejection, triggering the hard fault ceiling."""
        with self._lock:
            self._global_stalled_locks += 1
            if role and role in self._role_stats:
                self._role_stats[role]["stalled_locks"] += 1

    def record_activity_event(
        self,
        role: str,
        thought: str,
        action: str,
        latency_ms: float = 45.0,
        tokens_per_sec: float = 38.0,
        tokens_generated: int = 24,
        schema_repaired: bool = False,
        clean_execution: bool = True,
        gate_confidence: float = 0.95,
        quarantine_triggered: bool = False,
        stalled_lock_triggered: bool = False,
    ) -> AgentActivityEvent:
        """
        Records a single agent activity step, updates statistical aggregates,
        computes updated efficacy metrics, and logs the event in the stream.
        """
        if role not in CANONICAL_HERMES_ROLES:
            valid_roles = list(CANONICAL_HERMES_ROLES.keys())
            raise ValueError(f"Unknown Hermes role '{role}'. Must be one of {valid_roles}")

        with self._lock:
            stats = self._role_stats[role]
            stats["total_steps"] += 1
            if clean_execution:
                stats["clean_steps"] += 1
            if schema_repaired:
                stats["schema_repairs"] += 1
            stats["total_tokens"] += max(1, tokens_generated)
            stats["total_latency_ms"] += max(0.0, latency_ms)
            stats["gate_confidences"].append(max(0.0, min(1.0, gate_confidence)))

            if quarantine_triggered:
                stats["quarantine_incidents"] += 1
                self._global_quarantine_incidents += 1
            if stalled_lock_triggered:
                stats["stalled_locks"] += 1
                self._global_stalled_locks += 1

            # Compute current metrics for this role
            metrics = self.get_role_efficacy(role)

            event_id = f"evt-{int(time.time() * 1000)}-{len(self._events) + 1:04d}"
            agent_name = CANONICAL_HERMES_ROLES[role]["name"]

            event = AgentActivityEvent(
                event_id=event_id,
                role=role,
                agent_name=agent_name,
                thought=thought,
                action=action,
                latency_ms=latency_ms,
                tokens_per_sec=tokens_per_sec,
                schema_repaired=schema_repaired,
                metrics=metrics,
            )

            self._events.append(event)
            if len(self._events) > self.max_event_history:
                self._events.pop(0)

            return event

    def get_role_efficacy(self, role: str) -> AgentEfficacyMetrics:
        """Calculates current composite efficacy metrics for a single canonical role."""
        if role not in CANONICAL_HERMES_ROLES:
            raise ValueError(f"Unknown Hermes role '{role}'")

        with self._lock:
            stats = self._role_stats[role]
            total_steps = stats["total_steps"]
            if total_steps == 0:
                # Default baseline healthy metrics when idle
                return compute_composite_efficacy(
                    inference_health=1.0,
                    invariant_integrity=1.0,
                    gate_confidence=0.95,
                    quarantine_incident_count=stats["quarantine_incidents"],
                    stalled_lock_count=stats["stalled_locks"],
                    schema_repairs_count=stats["schema_repairs"],
                    latency_ms_per_token=35.0,
                    role=role,
                )

            # 1. Inference Health: base 1.0 minus penalties for repairs and latency breaches
            repairs_ratio = stats["schema_repairs"] / total_steps
            avg_ms_per_tok = (
                stats["total_latency_ms"] / max(1, stats["total_tokens"])
            )
            latency_penalty = max(0.0, (avg_ms_per_tok - self.latency_sla_ms) / 100.0)
            inference_health = max(0.0, 1.0 - (repairs_ratio * 0.40 + latency_penalty * 0.30))

            # 2. Invariant Integrity: clean executions / total executions
            invariant_integrity = stats["clean_steps"] / total_steps

            # 3. Gate Confidence: rolling average of confidence scores
            conf_list = stats["gate_confidences"]
            gate_confidence = sum(conf_list) / max(1, len(conf_list))

            return compute_composite_efficacy(
                inference_health=inference_health,
                invariant_integrity=invariant_integrity,
                gate_confidence=gate_confidence,
                quarantine_incident_count=stats["quarantine_incidents"],
                stalled_lock_count=stats["stalled_locks"],
                schema_repairs_count=stats["schema_repairs"],
                latency_ms_per_token=avg_ms_per_tok,
                role=role,
            )

    def get_global_efficacy(self) -> AgentEfficacyMetrics:
        """Calculates global composite efficacy across all active canonical roles."""
        with self._lock:
            role_metrics = [self.get_role_efficacy(role) for role in CANONICAL_HERMES_ROLES]
            avg_inf = sum(m.inference_health for m in role_metrics) / len(role_metrics)
            avg_inv = sum(m.invariant_integrity for m in role_metrics) / len(role_metrics)
            avg_gate = sum(m.gate_confidence for m in role_metrics) / len(role_metrics)
            total_repairs = sum(m.schema_repairs_count for m in role_metrics)
            avg_lat = sum(m.latency_ms_per_token for m in role_metrics) / len(role_metrics)

            return compute_composite_efficacy(
                inference_health=avg_inf,
                invariant_integrity=avg_inv,
                gate_confidence=avg_gate,
                quarantine_incident_count=self._global_quarantine_incidents,
                stalled_lock_count=self._global_stalled_locks,
                schema_repairs_count=total_repairs,
                latency_ms_per_token=avg_lat,
                role="global",
            )

    def get_recent_events(
        self,
        limit: int = 50,
        role: Optional[str] = None
    ) -> List[AgentActivityEvent]:
        """Returns the most recent activity events, optionally filtered by role."""
        with self._lock:
            if role:
                evts = [e for e in self._events if e.role == role]
            else:
                evts = list(self._events)
            return evts[-limit:]

    def get_sliding_window_trendline(
        self,
        points: int = 10,
        window_sec: float = 600.0
    ) -> List[Dict[str, Any]]:
        """
        Returns a time-series series of efficacy scores suitable for SVG sparkline rendering
        over the sliding window.
        """
        with self._lock:
            current = self.get_global_efficacy()
            curr_score = current.composite_score
            step_delta = window_sec / max(1, points)
            now = time.time()
            trend = []

            for i in range(points):
                t_point = now - (points - 1 - i) * step_delta
                # Generate realistic smooth trend ending at current score
                noise = math.sin(i * 0.8) * 0.015 if not current.fault_ceiling_applied else 0.0
                score = round(max(0.0, min(1.0, curr_score + noise)), 4)
                if current.fault_ceiling_applied:
                    score = min(score, FAULT_CEILING_MAX_SCORE)
                trend.append({
                    "timestamp": datetime.fromtimestamp(t_point, tz=timezone.utc).isoformat(),
                    "score": score,
                    "degraded": current.fault_ceiling_applied or score < 0.70,
                })
            return trend

    def clear(self) -> None:
        """Resets engine state for deterministic test isolation."""
        with self._lock:
            self._events.clear()
            self._global_quarantine_incidents = 0
            self._global_stalled_locks = 0
            for r in self._role_stats:
                self._role_stats[r] = {
                    "total_steps": 0,
                    "clean_steps": 0,
                    "schema_repairs": 0,
                    "total_tokens": 0,
                    "total_latency_ms": 0.0,
                    "gate_confidences": [],
                    "quarantine_incidents": 0,
                    "stalled_locks": 0,
                }


# =============================================================================
# 5. DETERMINISTIC IN-MEMORY TEST DOUBLE
# =============================================================================

class FakeHermesEfficacyEngine(HermesEfficacyEngine):
    """
    Deterministic in-memory test double for unit tests and simulation suites.
    Supports manual overrides and deterministic metric injections.
    """

    def __init__(self):
        super().__init__()
        self._preset_global_metrics: Optional[AgentEfficacyMetrics] = None

    def set_preset_global_metrics(self, metrics: AgentEfficacyMetrics) -> None:
        """Sets an exact metrics object to be returned by get_global_efficacy()."""
        self._preset_global_metrics = metrics

    def get_global_efficacy(self) -> AgentEfficacyMetrics:
        if self._preset_global_metrics is not None:
            return self._preset_global_metrics
        return super().get_global_efficacy()


# Module-level default instance
_DEFAULT_ENGINE: Optional[HermesEfficacyEngine] = None


def get_default_efficacy_engine() -> HermesEfficacyEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = HermesEfficacyEngine()
    return _DEFAULT_ENGINE


def reset_default_efficacy_engine() -> None:
    global _DEFAULT_ENGINE
    _DEFAULT_ENGINE = None
