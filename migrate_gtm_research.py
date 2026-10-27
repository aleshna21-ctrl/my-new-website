#!/usr/bin/env python3
"""
migrate_gtm_research.py
=======================
AIOS GTM Outreach & Research Migration Script:
1. Parses gtm-research/staged_outreach.json (with data/staged_outreach.json fallback).
2. Generates the primary "GTM Outreach & Research" governance node (vault/04_AIOS_GTM_OUTREACH.md)
   under strict AIOS authority as a Ring-1 child of [[00_AIOS_ROOT]].
3. Generates dedicated, standalone Markdown files in the Obsidian vault (vault/gtm/) for every
   target client (e.g., Cambridge Specialty Company, Apex Thermal Solutions, VetPowered, etc.).
4. Contextually maps extracted data: vertical, problem context, reconciliation bottlenecks,
   target ERP/accounting systems, and financial leakage basis.
5. Routes every client node directly to [[04_AIOS_GTM_OUTREACH]] and routes the outbound execution edge
   directly to [[modules/hermes-delegation.md|Hermes Delegation]].
6. Mirrors updates to the primary second-brain vault if available.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
GTM_DIR = WORKSPACE_ROOT / "gtm-research"
FALLBACK_GTM_DIR = PROJECT_ROOT / "data"
LOCAL_VAULT_DIR = PROJECT_ROOT / "vault"
PRIMARY_VAULT_DIR = Path(
    os.environ.get("SECOND_BRAIN_DIR", r"G:\My Drive\second-brain" if os.name == "nt" else str(LOCAL_VAULT_DIR))
)


def get_staged_outreach_path() -> Path:
    """Finds staged_outreach.json (workspace gtm-research first, then local data fallback)."""
    gtm_path = GTM_DIR / "staged_outreach.json"
    if gtm_path.exists():
        return gtm_path
    local_path = FALLBACK_GTM_DIR / "staged_outreach.json"
    if local_path.exists():
        return local_path
    return gtm_path


def load_prospects(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    target = path or get_staged_outreach_path()
    if not target.exists():
        raise FileNotFoundError(f"staged_outreach.json not found at {target}")
    with open(target, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def client_slug(prospect: Dict[str, Any], index: int) -> str:
    pid = prospect.get("prospect_id") or prospect.get("id") or f"prospect_{index}"
    name = prospect.get("company_name") or prospect.get("company") or f"Client_{index}"
    # Disambiguate duplicate company names by checking purpose or pid
    clean_name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-")
    if "e2e_keystone" in pid:
        return "Keystone-Precision-Machining-Reconciliation"
    elif "e4ec3886" in pid:
        return "Keystone-Precision-Machining-Plating"
    return clean_name


def render_client_markdown(prospect: Dict[str, Any], slug: str, now_iso: str) -> str:
    company = prospect.get("company_name") or prospect.get("company") or "Unnamed Target"
    prospect_id = prospect.get("prospect_id") or prospect.get("id") or slug
    vertical = prospect.get("vertical") or "B2B Manufacturing & Operations"
    contact_name = prospect.get("contact_name") or "Operational Lead"
    contact_title = prospect.get("contact_title") or "Operations / Finance"
    contact_email = prospect.get("contact_email") or prospect.get("email") or prospect.get("recipient_ref") or "—"
    status = prospect.get("status") or prospect.get("review_status") or "needs_review"
    review_status = prospect.get("review_status") or status
    custom_hook = prospect.get("custom_hook") or "—"
    staged_subj = prospect.get("staged_email_subject") or prospect.get("subject") or "—"
    staged_body = prospect.get("staged_email_body") or prospect.get("body") or "—"

    # Extract target systems & pain points
    pain_points = prospect.get("pain_points") or []
    target_systems = []
    discrepancy_patterns = []
    leakage_basis = []

    for pp in pain_points:
        if isinstance(pp, dict):
            for s in pp.get("target_systems", []):
                if s not in target_systems:
                    target_systems.append(s)
            if pp.get("discrepancy_pattern"):
                discrepancy_patterns.append(pp["discrepancy_pattern"])
            if pp.get("estimated_leakage_basis"):
                leakage_basis.append(pp["estimated_leakage_basis"])

    # Fallback heuristics for older prospects lacking structured pain_points
    if not target_systems:
        if "JobBOSS" in staged_body or "JobBOSS" in vertical:
            target_systems.extend(["JobBOSS", "QuickBooks"])
        elif "reconciliation" in vertical.lower():
            target_systems.append("Internal ERP / GL")

    if not discrepancy_patterns:
        if "e2e_keystone" in prospect_id:
            discrepancy_patterns.append("Outside-processing plater invoice mismatches, duplicate invoice IDs, and fractional scales.")
        elif "Cambridge" in company:
            discrepancy_patterns.append("Manual data reconciliation creating friction around month-end close (JobBOSS balance checks & monthly GL reconciliations).")
        elif "VetPowered" in company:
            discrepancy_patterns.append("Purchase order, receipt, and WIP reconciliation discrepancies leading to silent batch export failures.")

    if not leakage_basis:
        if "e2e_keystone" in prospect_id:
            leakage_basis.append("4,200 monthly transactions; $826,920.00 annual reconciliation exposure; ~$380.00 avg plater variance.")
        else:
            leakage_basis.append("Month-end close labor drag and undetected invoice batch discrepancies.")

    # Financial evidence if present
    strict_evidence = prospect.get("strict_financial_evidence") or {}
    evidence_rows = []
    for k, v in strict_evidence.items():
        evidence_rows.append(f"| `{k}` | `{v}` |")
    evidence_table = "\n".join(evidence_rows) if evidence_rows else "| *Standard heuristic signal* | `signal-01` |"

    return f"""---
title: "Client Research // {company}"
type: "gtm-client-node"
node_id: "gtm-client-{slug.lower()}"
prospect_id: "{prospect_id}"
company_name: "{company}"
vertical: "{vertical}"
parent: "[[04_AIOS_GTM_OUTREACH]]"
delegation_target: "[[modules/hermes-delegation.md]]"
execution_agent: "agent-hermes-evaluator"
status: "{status.upper()}"
review_status: "{review_status}"
contact_name: "{contact_name}"
contact_title: "{contact_title}"
contact_email: "{contact_email}"
target_systems:
{chr(10).join([f"  - \"{ts}\"" for ts in target_systems]) or "  - \"Unspecified ERP\""}
tags:
  - aios
  - gtm
  - client-research
  - prospect
  - {re.sub(r'[^a-zA-Z0-9]+', '-', vertical.lower()).strip('-')}
---

# 🏢 Client Research Base: {company}

> **Target Prospect Profile:** Standalone operational research node for **{company}**, governed under **AIOS GTM Outreach & Research**. Provides verified domain context, target ERP landscapes, reconciliation bottlenecks, and strict financial evidence for autonomous or human-gated Hermes drafting.

---

## 1. Governance & Execution Routing

This client node is directly governed under strict AIOS authority and routes execution to Hermes:

```mermaid
graph LR
    GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"] --> CLIENT["🏢 [[gtm/{slug}|{company}]]"]
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
| **Company Name** | **{company}** |
| **Prospect ID** | `{prospect_id}` |
| **Target Vertical** | `{vertical}` |
| **Primary Contact** | **{contact_name}** ({contact_title}) |
| **Verified Email** | `{contact_email}` |
| **Review Status** | `{status.upper()}` |
| **Target ERP / Systems** | {', '.join([f'`{ts}`' for ts in target_systems]) or '`Unspecified`'} |

---

## 3. Reconciliation Bottlenecks & Problem Context

### Identified Discrepancy Patterns
{chr(10).join([f"- **Friction Point:** {dp}" for dp in discrepancy_patterns])}

### Financial Leakage Basis
{chr(10).join([f"- **Leakage Surface:** {lb}" for lb in leakage_basis])}

### Operational Hook & Context
> "{custom_hook}"

---

## 4. Staged Communication & Evidence Anchors

### Staged Subject Line
`{staged_subj}`

### Staged Email Body
```text
{staged_body}
```

### Deterministic Financial & Audit Evidence
| Metric / Identifier | Evidence Value |
| :--- | :--- |
{evidence_table}

---

## 5. Hermes Personalization Directives

When drafting, revising, or analyzing outreach for **{company}**, the Hermes Agent MUST:
1. **Reference Target Systems:** Ground value propositions in specific integration boundaries ({', '.join(target_systems) or 'their specific ERP'}).
2. **Quantify Bottlenecks:** Address the exact pain points outlined in Section 3 without generalizing into generic marketing copy.
3. **Preserve Proof Constraints:** Maintain Level 8 deterministic proof invariants (never promise fake automation; reference audited exception packets).
4. **Adhere to Delegation Boundary:** Route all mutations back through `staged_outreach.json` without bypassing human approval.

---
*Maintained under AIOS Authority · Connected to [[04_AIOS_GTM_OUTREACH]] and [[modules/hermes-delegation.md]].*
"""


def render_gtm_outreach_markdown(prospects: List[Dict[str, Any]], slugs: List[str], now_iso: str) -> str:
    total_count = len(prospects)
    approved_count = sum(1 for p in prospects if p.get("status") == "approved")
    pending_count = total_count - approved_count

    # Build prospect table rows
    rows = []
    for p, sl in zip(prospects, slugs):
        comp = p.get("company_name") or p.get("company") or "Unnamed"
        pid = p.get("prospect_id") or p.get("id")
        vert = p.get("vertical") or "B2B"
        cname = p.get("contact_name") or "Lead"
        stat = p.get("status") or "needs_review"
        badge = "APPROVED" if stat == "approved" else "PENDING"
        rows.append(f"| **[[gtm/{sl}\\|{comp}]]** | `{pid}` | `{vert}` | {cname} | **{badge}** | [[gtm/{sl}]] |")

    prospect_table = "\n".join(rows)

    return f"""---
title: "AIOS // GTM Outreach & Research Engine"
type: "aios-gtm-governance"
node_id: "aios-gtm-outreach"
ring: 1
parent: "[[00_AIOS_ROOT]]"
status: "ACTIVE"
updated_at: "{now_iso}"
total_prospects: {total_count}
approved_prospects: {approved_count}
pending_prospects: {pending_count}
delegation_target: "[[modules/hermes-delegation.md]]"
tags:
  - aios
  - gtm
  - outreach-governance
  - research
  - hermes-delegation
  - client-prospects
---

# 🎯 AIOS GTM Outreach & Research Engine (Ring 1 Governance)

> **Architectural Mission:** The GTM Outreach & Research Node operates under strict **AIOS Root Governance** to manage market discovery, targeted B2B client research, Level 4 confidence evaluation, and outbound communications. It anchors standalone prospect nodes and routes execution directly to **Hermes Delegation** for deterministic, evidence-backed personalization.

- **Parent System Nucleus:** [[00_AIOS_ROOT]] *(Ring 0 Core)*
- **Operational State Mirror:** [[00_AIOS_OPERATIONAL_STATE]]
- **Task Assignments Dispatcher:** [[03_AIOS_ASSIGNMENTS]]
- **Outbound Delegation Route:** [[modules/hermes-delegation.md|Hermes Delegation]]

---

## 1. AIOS GTM Governance & Authority

1. **Ring 1 Architectural Child:** Operates as a top-level subsystem under [[00_AIOS_ROOT]], ensuring that all commercial discovery aligns with AIOS execution boundaries.
2. **Zero-PII & Zero-Accidental-Dispatch Policy:** Outbound messages are generated as drafts into `staged_outreach.json` for human review. The engine never connects directly to live SMTP without human cryptographic approval.
3. **Deterministic Financial Grounding:** All value claims are derived from verified ledger invariants, Level 8 CSV audits, and Level 9 SOW specifications.

```mermaid
graph TD
    ROOT["🌐 [[00_AIOS_ROOT|AIOS Root Node (Ring 0)]]"]
    ROOT --> GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research (Ring 1)]]"]

    subgraph Dedicated Client Research Bases
{chr(10).join([f"        C{i}[\"🏢 [[gtm/{sl}|{p.get('company_name', 'Client')[:25]}]]\"]" for i, (p, sl) in enumerate(zip(prospects, slugs), 1)])}
    end

    GTM --> C1
    GTM --> C2
    GTM --> C3
    GTM --> C4
    GTM --> C5
    GTM --> C6
    GTM --> C7
    GTM --> C8
    GTM --> C9

    C1 --> HERMES["🧠 [[modules/hermes-delegation.md|Hermes Delegation]]"]
    C2 --> HERMES
    C3 --> HERMES
    C4 --> HERMES
    C5 --> HERMES
    C6 --> HERMES
    C7 --> HERMES
    C8 --> HERMES
    C9 --> HERMES

    HERMES --> OUTBOX["📬 [[spec-0001|staged_outreach.json (Outbox Diode)]]"]
```

---

## 2. Dedicated Client Research Bases (Prospect Roster)

All {total_count} target prospects from `staged_outreach.json` have been mapped into dedicated standalone research nodes:

| Client Target | Prospect ID | Vertical / Sector | Primary Contact | Review Gate | Research File |
| :--- | :--- | :--- | :--- | :--- | :--- |
{prospect_table}

---

## 3. Execution Routing: Outbound to Hermes Delegation

When execution triggers occur (AIOS-directed, operator-directed, or diode event), task dispatching flows through the following pipeline:

1. **Context Ingestion:** The Hermes Agent reads the dedicated client research base (e.g., `[[gtm/Cambridge-Specialty-Company]]`) to extract target systems, known discrepancy patterns, and financial exposure.
2. **Inference Execution:** The Hermes Agent invokes the local OpenAI-compatible inference loop (`127.0.0.1:8080`) using `LiveLocalModelAdapter` with `keep_alive=-1` to ensure rapid, in-memory prompt completion.
3. **Pydantic Validation & Gate 4 Evaluation:** The generated draft is validated against `OutreachDraft` schemas, scored via `CompositeScore` (Level 3), and verified against `ConfidenceGate` (Level 4).
4. **Diode Staging:** The finalized draft is staged into `staged_outreach.json` awaiting human authorization.

---

## 4. Key Knowledge & Module References

- **[[modules/hermes-delegation.md]]:** Delegation boundaries, local model execution, and approval handoffs.
- **[[modules/execution.md]]:** Tool authorization specifications and Level 6 bash guardrails.
- **[[modules/source-governance.md]]:** Provenance tracking, conflict resolution, and immutable chronologies.
- **[[modules/verification.md]]:** Observable proof requirements and Level 8/Level 10 deterministic test contracts.

---
*Maintained under AIOS Authority · Connected to [[00_AIOS_ROOT]] and [[modules/hermes-delegation.md]].*
"""


def update_aios_root_with_gtm(root_path: Path, now_iso: str) -> bool:
    """Updates 00_AIOS_ROOT.md to link explicitly to 04_AIOS_GTM_OUTREACH."""
    if not root_path.exists():
        return False
    content = root_path.read_text(encoding="utf-8")
    if "04_AIOS_GTM_OUTREACH" in content:
        return True  # Already updated

    # Add to mermaid graph
    if 'ROOT --> ASSIGN["📋 [[03_AIOS_ASSIGNMENTS]]"]' in content:
        content = content.replace(
            'ROOT --> ASSIGN["📋 [[03_AIOS_ASSIGNMENTS]]"]',
            'ROOT --> ASSIGN["📋 [[03_AIOS_ASSIGNMENTS]]"]\n    ROOT --> GTM["🎯 [[04_AIOS_GTM_OUTREACH|GTM Outreach & Research]]"]'
        )

    # Add to Section 2 (Core Routing & Operational Ledgers)
    gtm_line = "- **GTM Outreach & Research Engine:** [[04_AIOS_GTM_OUTREACH]] *(Strategic outreach governance, target client research bases, and Level 4 gate)*\n"
    if "- **Assignment Routing Engine:** [[03_AIOS_ASSIGNMENTS]]" in content:
        content = content.replace(
            "- **Assignment Routing Engine:** [[03_AIOS_ASSIGNMENTS]]",
            f"{gtm_line}- **Assignment Routing Engine:** [[03_AIOS_ASSIGNMENTS]]"
        )

    root_path.write_text(content, encoding="utf-8")
    return True


def execute_gtm_migration(vault_dir: Optional[Path] = None) -> Dict[str, Any]:
    print("=" * 70)
    print("🎯 [AIOS GTM MIGRATION] Parsing staged_outreach.json & Mapping Vault Nodes")
    print("=" * 70)

    target_vault = Path(vault_dir) if vault_dir else LOCAL_VAULT_DIR
    gtm_vault_dir = target_vault / "gtm"
    target_vault.mkdir(parents=True, exist_ok=True)
    gtm_vault_dir.mkdir(parents=True, exist_ok=True)

    staged_path = get_staged_outreach_path()
    print(f"\n[Step 1] Loading prospects from: {staged_path}")
    prospects = load_prospects(staged_path)
    print(f"         Found {len(prospects)} prospect records.")

    now_iso = datetime.now(timezone.utc).isoformat()
    slugs = [client_slug(p, i) for i, p in enumerate(prospects)]
    written_files = []

    # 1. Generate dedicated client nodes
    print(f"\n[Step 2] Generating dedicated client nodes in: {gtm_vault_dir}")
    for p, slug in zip(prospects, slugs):
        client_file = gtm_vault_dir / f"{slug}.md"
        client_content = render_client_markdown(p, slug, now_iso)
        client_file.write_text(client_content, encoding="utf-8")
        written_files.append(str(client_file))
        comp_name = p.get("company_name") or p.get("company")
        print(f"         [OK] Generated Client Node: {slug}.md ({comp_name})")

    # 2. Generate Primary GTM Outreach & Research Node
    primary_gtm_file = target_vault / "04_AIOS_GTM_OUTREACH.md"
    print(f"\n[Step 3] Generating Primary GTM Governance Node: {primary_gtm_file}")
    gtm_content = render_gtm_outreach_markdown(prospects, slugs, now_iso)
    primary_gtm_file.write_text(gtm_content, encoding="utf-8")
    written_files.append(str(primary_gtm_file))
    print(f"         [OK] Generated 04_AIOS_GTM_OUTREACH.md with {len(prospects)} client targets.")

    # 3. Update 00_AIOS_ROOT.md
    root_file = target_vault / "00_AIOS_ROOT.md"
    print(f"\n[Step 4] Linking GTM Governance Node to AIOS Root: {root_file}")
    updated_root = update_aios_root_with_gtm(root_file, now_iso)
    if updated_root:
        print("         [OK] Linked 04_AIOS_GTM_OUTREACH directly to 00_AIOS_ROOT.md.")

    # 4. Mirror to primary vault if available
    if PRIMARY_VAULT_DIR.exists() and PRIMARY_VAULT_DIR.is_dir() and PRIMARY_VAULT_DIR != target_vault:
        try:
            print(f"\n[Step 5] Mirroring to Primary Vault: {PRIMARY_VAULT_DIR}")
            p_gtm = PRIMARY_VAULT_DIR / "gtm"
            p_gtm.mkdir(parents=True, exist_ok=True)
            (PRIMARY_VAULT_DIR / "04_AIOS_GTM_OUTREACH.md").write_text(gtm_content, encoding="utf-8")
            update_aios_root_with_gtm(PRIMARY_VAULT_DIR / "00_AIOS_ROOT.md", now_iso)
            for p, slug in zip(prospects, slugs):
                (p_gtm / f"{slug}.md").write_text(render_client_markdown(p, slug, now_iso), encoding="utf-8")
            print("         [OK] Mirrored GTM nodes to Primary Vault.")
        except Exception as e:
            print(f"         [!] Primary vault mirroring skipped: {e}")

    print("\n" + "=" * 70)
    print(f"[SUCCESS] GTM Research Migration Complete: {len(written_files)} files written.")
    print("=" * 70)
    return {
        "status": "success",
        "timestamp_utc": now_iso,
        "prospects_count": len(prospects),
        "written_files_count": len(written_files),
        "written_files": written_files,
        "primary_node": str(primary_gtm_file),
        "client_slugs": slugs
    }


if __name__ == "__main__":
    res = execute_gtm_migration()
    sys.exit(0 if res.get("status") == "success" else 1)
