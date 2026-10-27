---
title: "Client Research // HarborGate Intermodal"
type: "gtm-client-node"
node_id: "gtm-client-harborgate-intermodal"
prospect_id: "gtm_73909b5d"
company_name: "HarborGate Intermodal"
vertical: "Maritime Freight/NVOCC"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Nadia Chen"
contact_title: "Head of Finance & Compliance"
contact_email: "billing-audit@harborgateintl.com"
target_systems:
  - "Magaya Supply Chain"
  - "QuickBooks Online"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - maritime-freight-nvocc
---

# 🏢 Client Research Base: HarborGate Intermodal

> **Target Prospect Profile:** Standalone operational research node for **HarborGate Intermodal**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/HarborGate-Intermodal|HarborGate Intermodal]]"]
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
| **Company Name** | **HarborGate Intermodal** |
| **Prospect ID** | `gtm_73909b5d` |
| **Target Vertical** | `Maritime Freight/NVOCC` |
| **Primary Contact** | **Nadia Chen** (Head of Finance & Compliance) |
| **Verified Email** | `billing-audit@harborgateintl.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `Magaya Supply Chain`, `QuickBooks Online` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Chassis split fees and congestion surcharges absorbed instead of being billed through to consignees.

### Financial Leakage Basis
- **Leakage Surface:** Unbilled accessorials and carrier chassis bill discrepancies

### Operational Hook & Context
> "Reconciling drayage chassis split fees and terminal accessorials against customer freight invoices."

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Stopping chassis fee & terminal surcharge pass-through leakage`

### Staged Email Body
```text
Nadia,

For mid-sized NVOCCs, unbilled chassis splits and terminal wait-time surcharges represent a consistent 1.5% to 3% margin leak simply because carrier drayage bills arrive weeks after consignee invoices are finalized.

Our reconciliation pipeline programmatically matches late-arriving drayage invoices to original booking files and automatically stages supplementary billing entries for review.

Could we share a 5-minute walkthrough showing how HarborGate can automate drayage pass-through reconciliations?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **HarborGate Intermodal**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (Magaya Supply Chain, QuickBooks Online).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
