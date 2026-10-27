---
title: "Client Research // Apex Thermal Solutions"
type: "gtm-client-node"
node_id: "gtm-client-apex-thermal-solutions"
prospect_id: "gtm_bbbf06f3"
company_name: "Apex Thermal Solutions"
vertical: "Commercial Refrigeration/HVAC"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "NEEDS_REVIEW"
review_status: "needs_review"
contact_name: "Marcus Vance"
contact_title: "Vice President of Field Operations"
contact_email: "ops-billing@apexthermalsolutions.com"
target_systems:
  - "ServiceTitan"
  - "QuickBooks Enterprise"
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - commercial-refrigeration-hvac
---

# 🏢 Client Research Base: Apex Thermal Solutions

> **Target Prospect Profile:** Standalone operational research node for **Apex Thermal Solutions**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/Apex-Thermal-Solutions|Apex Thermal Solutions]]"]
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
| **Company Name** | **Apex Thermal Solutions** |
| **Prospect ID** | `gtm_bbbf06f3` |
| **Target Vertical** | `Commercial Refrigeration/HVAC` |
| **Primary Contact** | **Marcus Vance** (Vice President of Field Operations) |
| **Verified Email** | `ops-billing@apexthermalsolutions.com` |
| **Review Status** | `NEEDS_REVIEW` |
| **Target ERP / Systems** | `ServiceTitan`, `QuickBooks Enterprise` |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
- **Friction Point:** Emergency compressor replacements credited by OEM distributors at differing core values than field POs.

### Financial Leakage Basis
- **Leakage Surface:** Unclaimed vendor core credits and mismatched supply house counter tickets

### Operational Hook & Context
> "Reconciling 15+ technician van inventories and OEM core credits against ServiceTitan work orders before monthly close."

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`Automating OEM parts credit & work order reconciliation for Apex Thermal`

### Staged Email Body
```text
Marcus,

In multi-tech commercial refrigeration operations running ServiceTitan, emergency compressor and coil swap tickets frequently diverge from distributor credit memos—especially when core returns sit at supply houses unapplied.

We build deterministic financial reconciliation pipelines that automatically 3-way match field technician part requisitions, vendor counter receipts, and OEM credit statements. It flags core-credit leakage within 24 hours rather than during month-end audit cleanups.

Could we run a sample batch of last month's supply house tickets against your open work orders to benchmark your credit capture?
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
| *Standard heuristic signal* | `signal-01` |

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **Apex Thermal Solutions**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries (ServiceTitan, QuickBooks Enterprise).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
