---
title: "Client Research // Cambridge Specialty Company"
type: "gtm-client-node"
node_id: "gtm-client-cambridge-specialty-company"
prospect_id: "gtm_001"
company_name: "Cambridge Specialty Company"
vertical: "Precision Manufacturing / B2B"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "APPROVED"
review_status: "needs_review"
contact_name: "Operational Lead"
contact_title: "Operations / Finance"
contact_email: "ap-ar@cambridgespecialty.com"
target_systems:
  - "JobBOSS"
  - "QuickBooks"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - precision-manufacturing-b2b
---

# 🏢 Client Research Base: Cambridge Specialty Company

> **Target Prospect Profile:** Standalone operational research node for **Cambridge Specialty Company**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/Cambridge-Specialty-Company|Cambridge Specialty Company]]"]
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
| **Company Name** | **Cambridge Specialty Company** |
| **Prospect ID** | `gtm_001` |
| **Target Vertical** | `Precision Manufacturing / B2B` |
| **Primary Contact** | **Operational Lead** (Operations / Finance) |
| **Verified Email** | `ap-ar@cambridgespecialty.com` |
| **Review Status** | `APPROVED` |
| **Target ERP / Systems** | `JobBOSS`, `QuickBooks` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Manual data reconciliation creating friction around month-end close (JobBOSS balance checks & monthly GL reconciliations).

### Financial Leakage Basis
- **Leakage Surface:** Month-end close labor drag and undetected invoice batch discrepancies.

### Operational Hook & Context
> "—"

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Reconciliation bottlenecks at Cambridge Specialty Company`

### Staged Email Body
```text
Hi,

Noticed your team manages workflows where manual data reconciliation creates heavy friction around month-end close (JobBOSS balance checks and monthly GL reconciliations).

We build local-first pipelines that eliminate silent batch export failures. Worth a brief look?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **Cambridge Specialty Company**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (JobBOSS, QuickBooks).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
