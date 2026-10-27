---
title: "Client Research // Keystone Precision Machining"
type: "gtm-client-node"
node_id: "gtm-client-keystone-precision-machining-reconciliation"
prospect_id: "gtm_e2e_keystone_reconciliation"
company_name: "Keystone Precision Machining"
vertical: "Precision CNC / JobBOSS Reconciliation"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Brian Kelling"
contact_title: "General Manager"
contact_email: "purchasing@keystoneprecisioncnc.com"
target_systems:
  - "JobBOSS"
  - "QuickBooks"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - precision-cnc-jobboss-reconciliation
---

# 🏢 Client Research Base: Keystone Precision Machining

> **Target Prospect Profile:** Standalone operational research node for **Keystone Precision Machining**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/Keystone-Precision-Machining-Reconciliation|Keystone Precision Machining]]"]
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
| **Prospect ID** | `gtm_e2e_keystone_reconciliation` |
| **Target Vertical** | `Precision CNC / JobBOSS Reconciliation` |
| **Primary Contact** | **Brian Kelling** (General Manager) |
| **Verified Email** | `purchasing@keystoneprecisioncnc.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `JobBOSS`, `QuickBooks` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Outside-processing plater invoice mismatches, duplicate invoice IDs, and fractional scales.

### Financial Leakage Basis
- **Leakage Surface:** 4,200 monthly transactions; $826,920.00 annual reconciliation exposure; ~$380.00 avg plater variance.

### Operational Hook & Context
> "—"

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Keystone Precision: Automated JobBOSS Batch Quarantine & Plater PO Audit (12-Row Sample Verification)`

### Staged Email Body
```text
Brian,

Following our Statement of Work review for Keystone Precision Machining ($826,920.00 annual reconciliation exposure across 4,200 monthly JobBOSS and QuickBooks transactions), our offline reconciliation harness executed a zero-context Level 8 verification pass on the 12-row sample invoice batch.

Deterministic Audit Findings (StrictStr Preserved):
- Quarantined Negative/Fractional Invoice: INV-4459-QZJZ at -999.995 (2026-05-16)
- Quarantined Duplicate InvoiceID: INV-2059-IYIG at 226.74 (2026-03-09, 2 occurrences)
- Non-2-Decimal Scale Variances: INV-9783-WNNC (46) and INV-5960-WCJS (206.3)
- Clean Verified Invoices: 8 of 12 accepted; 4 quarantined before AP ledger posting

This isolates the exact outside-processing plater invoice mismatches (~168 incidents/mo at $380.00 avg impact) before accounts payable issues payment. Would you like to review the quarantined exception packet for Milestone 1 sign-off?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| `quarantined_negative_invoice` | `INV-4459-QZJZ` |
| `quarantined_negative_amount` | `-999.995` |
| `duplicate_invoice_id` | `INV-2059-IYIG` |
| `duplicate_invoice_amount` | `226.74` |
| `non_two_decimal_samples` | `['46', '206.3']` |
| `sow_annual_risk_exposure` | `826920.00` |
| `sow_direct_leakage` | `766080.00` |
| `sow_projected_net_savings` | `702882.00` |
| `sow_avg_plater_discrepancy` | `380.00` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **Keystone Precision Machining**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (JobBOSS, QuickBooks).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
