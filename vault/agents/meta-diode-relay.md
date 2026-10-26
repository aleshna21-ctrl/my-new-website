---
title: "Agent // Meta-Diode-Relay"
type: "aios-agent-node"
agent_id: "agent-meta-diode-relay"
role: "metadata_diode_and_relay"
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "2026-10-26T18:51:20.845878+00:00"
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
