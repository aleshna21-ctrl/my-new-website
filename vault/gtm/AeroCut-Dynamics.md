---
title: "Client Research // AeroCut Dynamics"
type: "gtm-client-node"
node_id: "gtm-client-aerocut-dynamics"
prospect_id: "gtm_33207f88"
company_name: "AeroCut Dynamics"
vertical: "Precision CNC"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Samantha Miller"
contact_title: "VP of Operations"
contact_email: "ops@aerocutdynamics.com"
target_systems:
  - "E2 Shop System"
  - "Global Shop Solutions"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - precision-cnc
---

# 🏢 Client Research Base: AeroCut Dynamics

> **Target Prospect Profile:** Standalone operational research node for **AeroCut Dynamics**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/AeroCut-Dynamics|AeroCut Dynamics]]"]
    CLIENT -->|contextual recall & personalized drafting| HERMES["🧠 [[modules/hermes-delegation.md|Hermes Delegation]]"]
    HERMES -->|staged draft verification (Level 4 Gate)| OUTBOX["📬 [[spec-0001|staged_outreach.json]]"]
```

- **Parent Authority Node:** [[04_AIOS_GTM_OUTREACH]] *(GTM Outreach & Research Engine)*
- **Outbound Execution Route:** [[modules/hermes-delegation.md|Hermes Delegation]] *(Local Model Adapter `keep_alive=-1` & Evaluator)*
- **Execution Agent:** `agent-hermes-evaluator`
- **Approval Policy:** Mandates Level 4 Confidence Gate review. Outbound email is strictly non-auto-sending.

---

## 2. Client Profile & Target Systems

| Attribute | Extracted Value |
| :--- | :--- |
| **Company Name** | **AeroCut Dynamics** |
| **Prospect ID** | `gtm_33207f88` |
| **Target Vertical** | `Precision CNC` |
| **Primary Contact** | **Samantha Miller** (VP of Operations) |
| **Verified Email** | `ops@aerocutdynamics.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `E2 Shop System`, `Global Shop Solutions` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Material distributor invoices showing unquoted cutting surcharges and weight discrepancies against certified bar stock receiving logs.

### Financial Leakage Basis
- **Leakage Surface:** Raw material weight discrepancies and unapproved freight/prep adders

### Operational Hook & Context
> "3-way matching raw aerospace titanium and 6061 bar stock invoices against E2 receiving logs and heat certs."

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Automated bar stock & cutting adder audit for AeroCut Dynamics`

### Staged Email Body
```text
Samantha,

Between drop fees, cutting charges, and alloy surcharges, metal distributor invoices often contain subtle line-item adjustments that bypass standard receiving checks in E2.

Our deterministic reconciliation scripts perform line-by-line verification of bar stock invoices against purchase order price breaks and certified received weights, ensuring no unapproved supplier markups slide through to job costs.

Could we benchmark your last quarter of raw material invoices against your PO pricing schedules?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **AeroCut Dynamics**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (E2 Shop System, Global Shop Solutions).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
