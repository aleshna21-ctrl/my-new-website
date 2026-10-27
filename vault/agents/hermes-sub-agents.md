---
title: "Agent // Hermes Sub-Agents Cluster"
type: "aios-agent-node"
agent_id: "agent-hermes-cluster"
role: "local_inference_and_rpc"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "2026-10-27T09:53:57.487287+00:00"
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
1. **Hermes Pipeline Tracer (`agent-hermes-tracer`):**
   - Role: `pipeline_tracer` · Status: `ACTIVE`
   - Autonomous tracer bullet verifying adapter wake-up and dynamically populating ledger.
2. **Hermes Agentic Evaluator (`agent-hermes-evaluator`):**
   - Role: `agentic_judge` · Status: `ACTIVE`
   - Implements JEV System-One judgment gates, cheap file reads, and diff triage.
3. **Hermes Diagnostic Probe (`agent-hermes-probe-worker`):**
   - Role: `diagnostic_probe` · Status: `ACTIVE`
   - Synthetic connectivity and latency monitor isolated via PROBE_LOCK.
4. **Hermes Model Adapter (`agent-hermes-model-adapter`):**
   - Role: `model_adapter` · Status: `ACTIVE`
   - Live loopback adapter on 127.0.0.1:8080 bridging upstream Ollama with keep_alive=-1.
5. **Hermes Gateway Daemon (`agent-hermes-gateway`):**
   - Role: `rpc_gateway` · Status: `ACTIVE`
   - Handles /gateway/v1/rpc with anti-replay timestamp & nonce authentication.

---
*Directly wired to [[00_AIOS_ROOT]].*
