---
title: "Client Research // Keystone Precision Machining"
type: "gtm-client-node"
node_id: "gtm-client-keystone-precision-machining-plating"
prospect_id: "gtm_e4ec3886"
company_name: "Keystone Precision Machining"
vertical: "Precision CNC"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Brian Kelling"
contact_title: "General Manager"
contact_email: "purchasing@keystoneprecisioncnc.com"
target_systems:
  - "JobBOSS²"
  - "Excel"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - precision-cnc
---

# 🏢 Client Research Base: Keystone Precision Machining

> **Target Prospect Profile:** Standalone operational research node for **Keystone Precision Machining**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/Keystone-Precision-Machining-Plating|Keystone Precision Machining]]"]
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
| **Company Name** | **Keystone Precision Machining** |
| **Prospect ID** | `gtm_e4ec3886` |
| **Target Vertical** | `Precision CNC` |
| **Primary Contact** | **Brian Kelling** (General Manager) |
| **Verified Email** | `purchasing@keystoneprecisioncnc.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `JobBOSS²`, `Excel` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Anodizing and heat-treat vendor invoices billed on gross lot quantities rather than delivered good parts, with missing cert tracking.

### Financial Leakage Basis
- **Leakage Surface:** Outside processing over-charges and traveler scrap tracking gaps

### Operational Hook & Context
> "Matching outside processing invoices (anodizing/heat-treat) against JobBOSS router piece counts and purchase orders."

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Automating outside processing PO reconciliation for Keystone Precision`

### Staged Email Body
```text
Brian,

When sending precision-machined components out for heat treat, plating, or passivation, vendor invoices frequently arrive with lot surcharges or piece counts that do not match the quantities accepted back on the traveler router in JobBOSS.

We provide a zero-loss financial reconciliation harness designed specifically for machine shops. It automatically flags discrepancies between outside service invoices, receiving records, and original PO quotes before accounts payable issues payment.

Would you be open to running a brief test comparing your last month of outside processing invoices against JobBOSS router receipts?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **Keystone Precision Machining**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (JobBOSS², Excel).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
