"""
tests/test_hermes_observability.py
==================================
Comprehensive Unit & Integration Test Suite for Hermes Observability Seam (Ticket 01).
Validates:
1. Canonical multi-agent matrix domain model across 4 roles.
2. Dual-access response contracts (AgentEfficacyMetrics, AgentActivityEvent).
3. 3-tier composite efficacy formulation (35% Inference, 35% Invariant, 30% Confidence).
4. Hard fault ceiling enforcement (<= 0.40) on quarantine or stalled lock events.
5. Real-time activity event logging, role filtering, and sliding window trendlines.
6. FakeHermesEfficacyEngine test double and singleton lifecycle.
"""

from __future__ import annotations

import json
import unittest

from hermes_observability import (
    CANONICAL_HERMES_ROLES,
    FAULT_CEILING_MAX_SCORE,
    WEIGHT_GATE_CONFIDENCE,
    WEIGHT_INFERENCE_HEALTH,
    WEIGHT_INVARIANT_INTEGRITY,
    AgentActivityEvent,
    AgentEfficacyMetrics,
    FakeHermesEfficacyEngine,
    HermesEfficacyEngine,
    compute_composite_efficacy,
    get_default_efficacy_engine,
    reset_default_efficacy_engine,
)


class TestHermesDomainModelAndContracts(unittest.TestCase):
    """Ticket 01: Canonical Domain Model & Response Contracts."""

    def test_canonical_roles_structure(self):
        """Verifies that all 4 canonical roles exist with expected badges and capabilities."""
        expected_roles = ["triage", "scout", "exec", "supervisor"]
        self.assertEqual(list(CANONICAL_HERMES_ROLES.keys()), expected_roles)

        self.assertEqual(CANONICAL_HERMES_ROLES["triage"]["badge"], "[TRIAGE]")
        self.assertEqual(CANONICAL_HERMES_ROLES["scout"]["badge"], "[SCOUT]")
        self.assertEqual(CANONICAL_HERMES_ROLES["exec"]["badge"], "[EXEC]")
        self.assertEqual(CANONICAL_HERMES_ROLES["supervisor"]["badge"], "[SUPERVISOR]")

        for role, data in CANONICAL_HERMES_ROLES.items():
            self.assertIn("name", data)
            self.assertIn("capability", data)
            self.assertIn("description", data)

    def test_agent_efficacy_metrics_dual_access(self):
        """Verifies dict indexing, typed properties, and JSON serializability of AgentEfficacyMetrics."""
        metrics = AgentEfficacyMetrics(
            composite_score=0.9625,
            inference_health=0.95,
            invariant_integrity=1.0,
            gate_confidence=0.92,
            degraded=False,
            fault_ceiling_applied=False,
            quarantine_incident_count=0,
            stalled_lock_count=0,
            schema_repairs_count=1,
            latency_ms_per_token=42.5,
            role="scout",
        )

        # Dictionary access
        self.assertIsInstance(metrics, dict)
        self.assertEqual(metrics["composite_score"], 0.9625)
        self.assertEqual(metrics["inference_health"], 0.95)
        self.assertEqual(metrics["invariant_integrity"], 1.0)
        self.assertEqual(metrics["gate_confidence"], 0.92)
        self.assertFalse(metrics["degraded"])
        self.assertFalse(metrics["fault_ceiling_applied"])
        self.assertEqual(metrics["quarantine_incident_count"], 0)
        self.assertEqual(metrics["stalled_lock_count"], 0)
        self.assertEqual(metrics["schema_repairs_count"], 1)
        self.assertEqual(metrics["latency_ms_per_token"], 42.5)
        self.assertEqual(metrics["role"], "scout")

        # Typed property access
        self.assertEqual(metrics.composite_score, 0.9625)
        self.assertEqual(metrics.inference_health, 0.95)
        self.assertEqual(metrics.invariant_integrity, 1.0)
        self.assertEqual(metrics.gate_confidence, 0.92)
        self.assertFalse(metrics.degraded)
        self.assertFalse(metrics.fault_ceiling_applied)
        self.assertEqual(metrics.quarantine_incident_count, 0)
        self.assertEqual(metrics.stalled_lock_count, 0)
        self.assertEqual(metrics.schema_repairs_count, 1)
        self.assertEqual(metrics.latency_ms_per_token, 42.5)
        self.assertEqual(metrics.role, "scout")
        self.assertTrue(metrics.is_healthy())

        # JSON serialization roundtrip
        serialized = json.dumps(metrics)
        deserialized = json.loads(serialized)
        self.assertEqual(deserialized["composite_score"], 0.9625)
        self.assertEqual(deserialized["role"], "scout")

    def test_agent_activity_event_dual_access(self):
        """Verifies AgentActivityEvent properties, nested metrics, and JSON serialization."""
        metrics = AgentEfficacyMetrics(0.95, 0.95, 1.0, 0.90)
        event = AgentActivityEvent(
            event_id="evt-001",
            role="triage",
            agent_name="Triage Agent",
            thought="Classifying incoming payload",
            action="actions.ask_jev",
            latency_ms=38.4,
            tokens_per_sec=45.2,
            schema_repaired=False,
            prompt_hash="hash-abc-123",
            sequence_ack="ack-000001",
            metrics=metrics,
        )

        self.assertIsInstance(event, dict)
        self.assertEqual(event.event_id, "evt-001")
        self.assertEqual(event.role, "triage")
        self.assertEqual(event.agent_name, "Triage Agent")
        self.assertEqual(event.thought, "Classifying incoming payload")
        self.assertEqual(event.action, "actions.ask_jev")
        self.assertEqual(event.latency_ms, 38.4)
        self.assertEqual(event.tokens_per_sec, 45.2)
        self.assertFalse(event.schema_repaired)
        self.assertEqual(event.prompt_hash, "hash-abc-123")
        self.assertEqual(event.sequence_ack, "ack-000001")
        self.assertIsNotNone(event.metrics)
        self.assertEqual(event.metrics.composite_score, 0.95)

        # JSON roundtrip
        json_str = json.dumps(event)
        self.assertIn('"event_id": "evt-001"', json_str)


class TestHermesCompositeEfficacyFormula(unittest.TestCase):
    """Ticket 01: Composite Efficacy Score Calculation & Penalty Ceiling."""

    def test_composite_formula_clean_baseline(self):
        """Verifies E = 0.35 * Inf + 0.35 * Inv + 0.30 * Gate for clean baseline."""
        # 0.35 * 1.0 + 0.35 * 1.0 + 0.30 * 1.0 = 1.0
        m = compute_composite_efficacy(
            inference_health=1.0,
            invariant_integrity=1.0,
            gate_confidence=1.0,
        )
        self.assertAlmostEqual(m.composite_score, 1.00, places=3)
        self.assertFalse(m.degraded)
        self.assertFalse(m.fault_ceiling_applied)
        self.assertTrue(m.is_healthy())

        # 0.35 * 1.0 + 0.35 * 1.0 + 0.30 * 0.90 = 0.35 + 0.35 + 0.27 = 0.97
        m2 = compute_composite_efficacy(
            inference_health=1.0,
            invariant_integrity=1.0,
            gate_confidence=0.90,
        )
        self.assertAlmostEqual(m2.composite_score, 0.97, places=3)
        self.assertTrue(m2.is_healthy())

    def test_hard_fault_ceiling_on_quarantine_incident(self):
        """Verifies that quarantine incidents immediately cap score at <= 0.40."""
        # Even with perfect 1.0 / 1.0 / 1.0 metrics, a quarantine incident must cap at 0.40
        m = compute_composite_efficacy(
            inference_health=1.0,
            invariant_integrity=1.0,
            gate_confidence=1.0,
            quarantine_incident_count=1,
        )
        self.assertLessEqual(m.composite_score, FAULT_CEILING_MAX_SCORE)
        self.assertEqual(m.composite_score, 0.40)
        self.assertTrue(m.fault_ceiling_applied)
        self.assertTrue(m.degraded)
        self.assertFalse(m.is_healthy())

    def test_hard_fault_ceiling_on_stalled_lock(self):
        """Verifies that stalled lock ejections immediately cap score at <= 0.40."""
        m = compute_composite_efficacy(
            inference_health=0.90,
            invariant_integrity=0.90,
            gate_confidence=0.85,
            stalled_lock_count=2,
        )
        self.assertLessEqual(m.composite_score, FAULT_CEILING_MAX_SCORE)
        self.assertEqual(m.composite_score, 0.40)
        self.assertTrue(m.fault_ceiling_applied)
        self.assertTrue(m.degraded)


class TestHermesEfficacyEngineLifecycle(unittest.TestCase):
    """Ticket 01: Engine Operation, Event Stream, and Test Doubles."""

    def setUp(self):
        self.engine = HermesEfficacyEngine(latency_sla_ms=55.0)

    def test_record_activity_and_role_metrics(self):
        """Verifies activity recording updates stats and returns activity events."""
        event = self.engine.record_activity_event(
            role="scout",
            thought="Inspecting vault documents",
            action="actions.jev_file_read",
            latency_ms=40.0,
            tokens_per_sec=42.0,
            tokens_generated=30,
            schema_repaired=False,
            clean_execution=True,
            gate_confidence=0.95,
        )

        self.assertEqual(event.role, "scout")
        self.assertEqual(event.agent_name, "Scout & Auditor")
        self.assertIsNotNone(event.metrics)
        self.assertGreater(event.metrics.composite_score, 0.85)

        # Check role-specific efficacy
        scout_m = self.engine.get_role_efficacy("scout")
        self.assertAlmostEqual(scout_m.invariant_integrity, 1.0)
        self.assertFalse(scout_m.degraded)

        # Unknown role validation
        with self.assertRaises(ValueError):
            self.engine.record_activity_event(
                role="nonexistent_role",
                thought="test",
                action="test",
            )

    def test_schema_repairs_penalize_inference_health(self):
        """Verifies that repeated schema repairs decrease inference health."""
        for _ in range(5):
            self.engine.record_activity_event(
                role="exec",
                thought="Executing script",
                action="actions.bash_tool",
                schema_repaired=True,
                clean_execution=True,
                gate_confidence=0.90,
            )

        exec_m = self.engine.get_role_efficacy("exec")
        self.assertLess(exec_m.inference_health, 1.0)
        self.assertEqual(exec_m.schema_repairs_count, 5)

    def test_global_efficacy_and_recent_events_filter(self):
        """Verifies global aggregation and recent event filtering."""
        self.engine.record_activity_event(role="triage", thought="Triage request", action="ask_jev")
        self.engine.record_activity_event(role="scout", thought="Reading file", action="jev_read")
        self.engine.record_activity_event(role="exec", thought="Running code", action="bash")

        global_m = self.engine.get_global_efficacy()
        self.assertEqual(global_m.role, "global")
        self.assertGreaterEqual(global_m.composite_score, 0.80)

        # Filter recent events by role
        scout_events = self.engine.get_recent_events(limit=10, role="scout")
        self.assertEqual(len(scout_events), 1)
        self.assertEqual(scout_events[0].role, "scout")

        all_events = self.engine.get_recent_events(limit=10)
        self.assertEqual(len(all_events), 3)

    def test_sliding_window_trendline(self):
        """Verifies sliding window trendline generation for SVG sparklines."""
        self.engine.record_activity_event(role="supervisor", thought="Evaluating gate", action="confidence_gate")
        trend = self.engine.get_sliding_window_trendline(points=10, window_sec=600.0)

        self.assertEqual(len(trend), 10)
        for point in trend:
            self.assertIn("timestamp", point)
            self.assertIn("score", point)
            self.assertIn("degraded", point)
            self.assertGreaterEqual(point["score"], 0.0)
            self.assertLessEqual(point["score"], 1.0)

    def test_fake_hermes_efficacy_engine_preset(self):
        """Verifies deterministic in-memory test double overrides."""
        fake = FakeHermesEfficacyEngine()
        preset = AgentEfficacyMetrics(0.9999, 1.0, 1.0, 1.0, role="preset")
        fake.set_preset_global_metrics(preset)

        res = fake.get_global_efficacy()
        self.assertEqual(res.composite_score, 0.9999)
        self.assertEqual(res.role, "preset")

    def test_singleton_lifecycle(self):
        """Verifies get_default_efficacy_engine() and reset_default_efficacy_engine()."""
        reset_default_efficacy_engine()
        eng1 = get_default_efficacy_engine()
        eng2 = get_default_efficacy_engine()
        self.assertIs(eng1, eng2)

        reset_default_efficacy_engine()
        eng3 = get_default_efficacy_engine()
        self.assertIsNot(eng1, eng3)


if __name__ == "__main__":
    unittest.main()
