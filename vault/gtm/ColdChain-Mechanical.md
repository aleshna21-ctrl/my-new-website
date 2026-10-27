---
title: "Client Research // ColdChain Mechanical"
type: "gtm-client-node"
node_id: "gtm-client-coldchain-mechanical"
prospect_id: "gtm_d0db6559"
company_name: "ColdChain Mechanical"
vertical: "Commercial Refrigeration/HVAC"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Elena Rostova"
contact_title: "Controller"
contact_email: "ap@coldchainmechanical.com"
target_systems:
  - "Jonas Premier"
  - "Sage Intacct"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - commercial-refrigeration-hvac
---

# 🏢 Client Research Base: ColdChain Mechanical

> **Target Prospect Profile:** Standalone operational research node for **ColdChain Mechanical**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/ColdChain-Mechanical|ColdChain Mechanical]]"]
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
| **Company Name** | **ColdChain Mechanical** |
| **Prospect ID** | `gtm_d0db6559` |
| **Target Vertical** | `Commercial Refrigeration/HVAC` |
| **Primary Contact** | **Elena Rostova** (Controller) |
| **Verified Email** | `ap@coldchainmechanical.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `Jonas Premier`, `Sage Intacct` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Weekend supermarket emergency call-outs billed at overtime without corresponding customer billable rate adjustments.

### Financial Leakage Basis
- **Leakage Surface:** Unbilled labor rate differentials and technician van stock slippage

### Operational Hook & Context
> "Eliminating margin leakage between supermarket emergency dispatch overtime and Jonas job-costing ledgers."

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Reconciliation check: Jonas job costing vs. supply house invoices`

### Staged Email Body
```text
Elena,

When commercial refrigeration crews handle supermarket emergency line breaks over the weekend, parts pulled from consignment and overtime hours often hit Jonas after billing cycles have already generated client invoices.

Our system runs an automated reconciliation harness that continuously flags unlinked supply-house invoices and unbilled technician hours before invoicing closes, preventing margin erosion on major accounts.

Are you open to seeing how our automated audit ledger isolates unbilled emergency WIP before your next financial review?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **ColdChain Mechanical**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (Jonas Premier, Sage Intacct).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
