/**
 * JEV + Mark LVI + Modular Second Brain Unified Frontend Engine (jev-omnibus.js)
 * Zero external dependencies. Works over http://127.0.0.1:5050 AND standalone file:// protocol.
 * Peer-Review Certified:
 *   - StrictStr Financial Guard: Monetary values never pass through Number/parseFloat; rendered via textContent.
 *   - Mark LVI Outcome Contract: done | unverified | failed | ask | started + Reversible Undo Stack + UI Confirmation Token.
 *   - Untrusted-Content Boundary: <<<UNTRUSTED_DATA_START>>> ... <<<UNTRUSTED_DATA_END>>> defanging.
 *   - JEV System-One Engine: noul, choice, score, Confidence Gating (<0.50, 0.50-0.90, >0.90), Levels 1-10, 7 Market Judgments -> 5 Rungs.
 *   - Zero-CDN Ring & Minimal 3D Obsidian Renderers (Concentric 4-Ring 2D + Tilted 3D Orbital Rings + 3D Fibonacci Sphere).
 */
(function (global) {
  'use strict';

  const UNTRUSTED_START = '<<<UNTRUSTED_DATA_START>>>';
  const UNTRUSTED_END = '<<<UNTRUSTED_DATA_END>>>';

  function wrapUntrusted(rawText, sourceLabel) {
    const safe = String(rawText == null ? '' : rawText).split(UNTRUSTED_END).join('[DEFANGED_END_MARKER]');
    return `${UNTRUSTED_START}[source=${sourceLabel || 'vault_record'}]\n${safe}\n${UNTRUSTED_END}`;
  }

  // Embedded canonical dataset synchronized from g:\My Drive\second-brain, c:\Users\alesh\jev-workspace, and Mark-LVI-main
  const DEFAULT_OMNIBUS = {
    schema_version: '2.0-omnibus',
    generated_at_utc: '2026-10-22T15:05:00Z',
    financial_strict_strings: {
      annual_risk_exposure_usd: '$826,920.00',
      projected_savings_usd: '$702,882.00',
      precision_canary_usd: '9007199254740993.0001 USD',
      max_position_cap_usd: '$50.00',
      max_loss_cap_usd: '$25.00',
      jev_1m_calls_cost_usd: '$16.80',
      sota_1m_calls_cost_usd: '$3,500.00',
      ledger_invariant_formula: '12 == 10 + 1 + 1 (PASS)'
    },
    second_brain: {
      version: 2,
      assembled_sha256: '7343B1C3051C560EEC99E488A8A5F37F45D9606CC51A9AF288B52ABC5564C6C6',
      rings: [
        { ring: 0, name: 'Ring 0: Shared Core', color: '#38bdf8' },
        { ring: 1, name: 'Ring 1: Second Brain Governance (9 ON, 1 OFF)', color: '#a78bfa' },
        { ring: 2, name: 'Ring 2: JEV Trading System (9 Roles + 3 Facades)', color: '#10b981' },
        { ring: 3, name: 'Ring 3: Workspace Diodes & Mark LVI Engine', color: '#f59e0b' }
      ],
      nodes: [
        // Ring 0
        {
          id: 'core.md',
          label: 'Second Brain Core',
          ring: 0,
          group: 'core',
          status: 'active',
          path: 'g:/My Drive/second-brain/core.md',
          tags: ['core', 'second-brain', '4-part-taxonomy'],
          requires: [],
          summary: 'Shared base instructions: 4-part structure, explicit module states (shared, conditional, disabled), source precedence.',
          content: '# Second Brain System Instructions\n\nOperate as a modular Second Brain. Apply the shared core throughout; apply a specialist module only when its activation condition matches the task. Module inclusion is not permission to perform its actions.\n\n1. System Architecture & Taxonomy (Source Governance, Knowledge & Memory)\n2. Core Operational Rules (Execution, Verification, Hermes Delegation, JEV Trading, Local Models)\n3. Persona & Cognitive Requirements\n4. Ongoing Project & Knowledge Indices'
        },
        // Ring 1: 9 Enabled + 1 Disabled Module
        {
          id: 'source-governance',
          label: 'Source Governance',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/source-governance.md',
          tags: ['governance', 'provenance', 'section-1'],
          requires: ['core.md'],
          summary: 'Owns source authority & chronology. hermes-jev-loop-adaptation.md governs conflicting earlier JEV material.',
          content: '### Module: Source Governance\n**Activation:** Shared. **Owns:** source authority and provenance. **Requires:** Core.\n- Always treat hermes-jev-loop-adaptation.md as the latest pre-Second Brain edition.\n- Distinguish explicit user preferences, source requirements, and UNVERIFIED claims.'
        },
        {
          id: 'knowledge-memory',
          label: 'Knowledge & Memory',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/knowledge-memory.md',
          tags: ['memory', '9-layers', 'section-1'],
          requires: ['source-governance'],
          summary: '9-layer storage boundaries: Sources, Hot context, Durable memory, User preferences, Procedures, Cold context, Implementation, Runtime state, Project records.',
          content: '### Module: Knowledge & Memory\n**Activation:** Organizing, retrieving, or persisting knowledge. **Requires:** Source Governance.\nNever store installer scripts, credentials, balances, positions, quotes, or ephemeral process status in durable agent memory.'
        },
        {
          id: 'execution',
          label: 'Execution',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/execution.md',
          tags: ['execution', 'capabilities', 'section-2'],
          requires: ['source-governance', 'verification'],
          summary: 'Owns authorized work, capability discovery, actual tool schemas, and secret protection.',
          content: '### Module: Execution\n**Activation:** Performing or guiding work. **Requires:** Source Governance, Verification.\n- Separate missing capability, missing information, and missing authorization.\n- Apply Verification before claiming completion.\n- Apply JEV Trading for JEV architecture, setup, validation, or operation.'
        },
        {
          id: 'verification',
          label: 'Verification',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/verification.md',
          tags: ['verification', 'peer-review', 'section-2'],
          requires: ['source-governance'],
          summary: 'Requires observable proof, dated evidence, and strict separation of specification, test results, and runtime state.',
          content: '### Module: Verification\n**Activation:** Testing, reviewing, validating, or reporting completion.\n- Always test the behavior actually claimed.\n- Never call self-review independent peer review or label Codex assistance as Hermes.'
        },
        {
          id: 'hermes-delegation',
          label: 'Hermes Delegation',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/hermes-delegation.md',
          tags: ['hermes', 'delegation', 'section-2'],
          requires: ['execution', 'verification'],
          summary: 'Team routing without mandatory budget fields. Tracks PREPARED_LOCAL, QUEUED, REPLIED, VERIFIED, FAILED, BLOCKED.',
          content: '### Module: Hermes Delegation\n- Never require budget, token allocation, cost ceiling, or spending-plan fields for routine assignments.\n- Distinguish PREPARED_LOCAL, QUEUED, REPLIED, VERIFIED, FAILED, and BLOCKED.'
        },
        {
          id: 'jev-trading',
          label: 'JEV Trading',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/jev-trading.md',
          tags: ['jev', 'trading', 'risk-limits', 'section-2'],
          requires: ['source-governance', 'execution', 'verification'],
          summary: 'Deterministic code owns arithmetic/prices/risk; Jev supplies 7 typed judgments. Selects RUN, REDUCE, HOLD_LATE, RULES_ONLY, KILL.',
          content: '### Module: JEV Trading\n**The split:** Deterministic code owns arithmetic, state, strategy, prices, order sizes, risk, actions, and routing. Jev supplies seven typed judgments in one response: regime, direction, toxic flow, liquidity stress, quote environment, inventory pressure, and execution health.'
        },
        {
          id: 'local-models',
          label: 'Local Models',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/local-models.md',
          tags: ['qwen3', 'ollama', 'hermes', 'section-2'],
          requires: ['execution', 'verification'],
          summary: 'Verifies actual GPU/CPU, quantization, context limits, and live interface reachability on 127.0.0.1:8080.',
          content: '### Module: Local Models\nAlways distinguish published capabilities from the smaller quantization installed and verify a real response through 127.0.0.1:8080.'
        },
        {
          id: 'persona',
          label: 'Persona & Cognition',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/persona.md',
          tags: ['persona', 'architect', 'section-3'],
          requires: ['core.md'],
          summary: 'Systems architect & prompt engineer persona: thinks in modules, ownership, failure conditions, and deterministic vs probabilistic split.',
          content: '### Module: Persona\nAct as an expert systems architect, prompt engineer, and practical technical collaborator. Separate deterministic calculation from probabilistic judgment.'
        },
        {
          id: 'project-index',
          label: 'Project Index',
          ring: 1,
          group: 'module',
          status: 'enabled',
          path: 'g:/My Drive/second-brain/modules/project-index.md',
          tags: ['index', 'records', 'section-4'],
          requires: ['source-governance', 'knowledge-memory'],
          summary: 'Owns project pointers for Second Brain, Hermes team, Trading/JEV loop, and Local Qwen3 Thinking.',
          content: '### Module: Project Index\nPointers: Second Brain, Hermes team, Trading / JEV loop, Local Qwen3 Thinking (cyankiwi/Qwen3-4B-Thinking-2507-AWQ-4bit).'
        },
        {
          id: 'budgeting',
          label: 'Optional Budgeting (OFF)',
          ring: 1,
          group: 'optional',
          status: 'disabled',
          path: 'g:/My Drive/second-brain/optional/budgeting.md',
          tags: ['optional', 'disabled', 'budgeting'],
          requires: ['execution'],
          summary: 'Disabled by default in manifest.json. Routine handoffs require zero budget or token-allocation fields.',
          content: '### Optional Module: Budgeting\n**Default state:** Disabled. While disabled, imposes no assignment field, planning step, dispatch gate, or review requirement.'
        },
        // Ring 2: 9 JEV Roles + 3 Identity Facades
        {
          id: 'Market State Role',
          label: 'Market State Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Market State Role.md',
          tags: ['jev', 'role', 'master-template'],
          requires: ['jev-trading'],
          summary: 'Master JEV role template: transforms supplied quote & account state into validated Decimal market state.',
          content: '# Market State Role\nMaster role handler (`jev_roles/roles/market_state.py`). Converts raw quotes into strict Decimal state.'
        },
        {
          id: 'Asset Validator Role',
          label: 'Asset Validator Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Asset Validator Role.md',
          tags: ['jev', 'role', 'validator'],
          requires: ['jev-trading', 'Market State Role'],
          summary: 'Validates supported Alpaca spot crypto pair or US equity symbol and market-open status.',
          content: '# Asset Validator Role\nVerifies symbol eligibility and market hours before state construction.'
        },
        {
          id: 'Risk Guard Role',
          label: 'Risk Guard Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Risk Guard Role.md',
          tags: ['jev', 'role', 'risk-guard'],
          requires: ['jev-trading', 'Market State Role'],
          summary: 'Enforces hard deterministic ceilings ($50.00 max position, $25.00 max loss cap) before and after order pricing.',
          content: '# Risk Guard Role\nDeterministic hard ceilings: $50.00 max position exposure, $25.00 max loss cap. Strategy may tighten but never raise caps.'
        },
        {
          id: 'Fallback Supervisor Role',
          label: 'Fallback Supervisor',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Fallback Supervisor Role.md',
          tags: ['jev', 'role', 'rung-selector'],
          requires: ['Risk Guard Role', 'jev-trading'],
          summary: 'Selects RUN, REDUCE, HOLD_LATE, RULES_ONLY, or KILL by condition from state and 7 Jev judgments.',
          content: '# Fallback Supervisor Role\nMaps qualitative Jev judgments and risk state to the 5 Action Rungs without sequential escalation.'
        },
        {
          id: 'Policy Composer Role',
          label: 'Policy Composer Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Policy Composer Role.md',
          tags: ['jev', 'role', 'policy'],
          requires: ['Market State Role', 'Fallback Supervisor Role'],
          summary: 'Translates qualitative Jev regime/direction judgments and state into candidate BUY / SELL / HOLD policy.',
          content: '# Policy Composer Role\nSynthesizes candidate action from Market State and validated JevMarketJudgment.'
        },
        {
          id: 'Strategy Steward Role',
          label: 'Strategy Steward Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Strategy Steward Role.md',
          tags: ['jev', 'role', 'strategy'],
          requires: ['Policy Composer Role'],
          summary: 'Golden Cross 50/200 SMA deterministic calculation steward; can tighten risk but never raise caps.',
          content: '# Strategy Steward Role\nApplies 50/200 SMA Golden Cross filter over candidate policy.'
        },
        {
          id: 'Pricing Engine Role',
          label: 'Pricing Engine Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Pricing Engine Role.md',
          tags: ['jev', 'role', 'pricing'],
          requires: ['Strategy Steward Role', 'Risk Guard Role'],
          summary: 'Computes exact Decimal order quantity and limit price under RUN or REDUCE rung constraints.',
          content: '# Pricing Engine Role\nDeterministic Decimal order sizing and limit price calculation.'
        },
        {
          id: 'Broker Execution Role',
          label: 'Broker Execution Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Broker Execution Role.md',
          tags: ['jev', 'role', 'execution'],
          requires: ['Pricing Engine Role', 'execution'],
          summary: 'Executes dry/simulated intent checks; defaults to NOT_SENT in dry mode and enforces final risk guard.',
          content: '# Broker Execution Role\nDefault dry mode produces NOT_SENT; only explicitly armed simulation accepts local intents.'
        },
        {
          id: 'Control Plane Role',
          label: 'Control Plane Role',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Control Plane Role.md',
          tags: ['jev', 'role', 'control-plane'],
          requires: ['jev-trading', 'verification'],
          summary: 'Manages pause vs liquidation boundaries and finite 256-message LocalBus transport ceiling.',
          content: '# Control Plane Role\nSeparates pause (blocks new orders) from risk liquidation.'
        },
        {
          id: 'JEV Identity Boundaries',
          label: 'JEV Identity Boundaries',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/JEV Identity Boundaries.md',
          tags: ['jev', 'identities', 'facades', 'offline-verified'],
          requires: ['jev-trading', 'hermes-delegation'],
          summary: 'Three local application facades (JudgmentBoundary, ApplicationBoundary, OperatorBoundary); none is a remote or authenticated agent.',
          content: '# JEV Identity Boundaries\nThree local application facades: JudgmentBoundary (jev-market-judgment), ApplicationBoundary (jev-spot-scalper), OperatorBoundary (hermes-jev-operator).'
        },
        {
          id: 'Jev Market Judgment',
          label: 'Jev Market Judgment',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Jev Market Judgment.md',
          tags: ['jev', 'implementation', 'offline-verified', 'judgment-boundary'],
          requires: ['JEV Identity Boundaries'],
          summary: 'Identity ID: jev-market-judgment. Facade: JudgmentBoundary. Validate exactly 7 qualitative judgments; invalid/expired input becomes unavailable. No action, sizing or pricing authority.',
          content: '---\ntype: implementation-spec\nstatus: finalized\ntags: [jev, implementation, offline-verified]\ndependencies: ["[[JEV Identity Boundaries]]"]\n---\n# Jev Market Judgment\nIdentity ID: `jev-market-judgment`. Facade: `JudgmentBoundary`.\nValidate exactly seven qualitative judgments. Invalid, expired or cached-failed input becomes unavailable. No action, sizing or pricing authority.\nThis is an in-process responsibility boundary. It does not authenticate untrusted callers or create a Hermes Bot.'
        },
        {
          id: 'Hermes JEV Operator',
          label: 'Hermes JEV Operator',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/Hermes JEV Operator.md',
          tags: ['jev', 'implementation', 'offline-verified', 'operator-boundary'],
          requires: ['JEV Identity Boundaries', 'hermes-delegation'],
          summary: 'Identity ID: hermes-jev-operator. Facade: OperatorBoundary. Executes typed TickInput against local ApplicationBoundary.',
          content: '# Hermes JEV Operator\nIdentity ID: `hermes-jev-operator`. Facade: `OperatorBoundary`. Local in-process operator facade.'
        },
        {
          id: 'JEV Spot Scalper',
          label: 'JEV Spot Scalper',
          ring: 2,
          group: 'jev-role',
          status: 'verified',
          path: 'g:/My Drive/second-brain/JEV_Trading_System/JEV Spot Scalper.md',
          tags: ['jev', 'implementation', 'offline-verified', 'application-boundary'],
          requires: ['JEV Identity Boundaries', 'Jev Market Judgment'],
          summary: 'Identity ID: jev-spot-scalper. Facade: ApplicationBoundary. Enforces one run_id and symbol per application identity.',
          content: '# JEV Spot Scalper\nIdentity ID: `jev-spot-scalper`. Facade: `ApplicationBoundary`. Validates judgment via JudgmentBoundary before RoleRuntime.tick.'
        },
        // Ring 3: Workspace Diodes & Mark LVI
        {
          id: 'inbox-offline-snapshot',
          label: 'Inbox: Offline Snapshot',
          ring: 3,
          group: 'inbox',
          status: 'active',
          path: 'c:/Users/alesh/jev-workspace/hud-interface/inbox/offline_snapshot.json',
          tags: ['inbox', 'diode', 'snapshot'],
          requires: ['verification', 'project-index'],
          summary: 'Read-only exported snapshot from delivery-offline SQLite job_ledger.db and reconciliation harness.',
          content: 'Exported snapshot from offline_observer.py. Preserves StrictStr money and per-batch count invariant (received == accepted + quarantined + duplicates).'
        },
        {
          id: 'outbox-metadata-diode',
          label: 'Outbox: Metadata Diode',
          ring: 3,
          group: 'outbox',
          status: 'active',
          path: 'c:/Users/alesh/jev-workspace/notification-outbox/metadata_outbox.json',
          tags: ['outbox', 'diode', 'smtp-relay'],
          requires: ['execution', 'verification'],
          summary: 'Regex-scrubbed, zero-PII event outbox awaiting isolated SMTP TLS relay dispatch.',
          content: 'Air-gapped metadata diode outbox. Emits opaque event references and state transitions only—zero financial figures or draft bodies.'
        },
        {
          id: 'outbox-gtm-queue',
          label: 'Outbox: GTM Review Gate',
          ring: 3,
          group: 'outbox',
          status: 'active',
          path: 'c:/Users/alesh/jev-workspace/gtm-research/staged_outreach.json',
          tags: ['outbox', 'gtm', 'human-review'],
          requires: ['execution', 'hermes-delegation'],
          summary: 'Staged B2B reconciliation outreach drafts gated by content-hash revision lock and explicit operator approval.',
          content: 'GTM Human-Review Queue (Cambridge Specialty, VetPowered, Apex Thermal, ColdChain Mechanical). Approval records a decision; never auto-sends.'
        },
        {
          id: 'mark-lvi-engine',
          label: 'Mark LVI Assistant Core',
          ring: 3,
          group: 'assistant',
          status: 'active',
          path: 'c:/Users/alesh/Downloads/Mark-LVI-main/main.py',
          tags: ['mark-lvi', 'providers', 'outcome-guard'],
          requires: ['local-models', 'knowledge-memory', 'persona'],
          summary: 'Cross-platform voice & tool assistant with STT Whisper + Local LLM + Piper TTS, 5-word verified outcomes, and recallable memory.',
          content: 'Mark LVI Core: 0.16ms provider dispatch, faster-whisper CPU STT (1.16s warm), Piper neural TTS (15x realtime, 52 languages), <think> stream filter, 5-word outcome verification (done/unverified/failed/ask/started).'
        },
        {
          id: 'capability-policy',
          label: '5-Zone Capability Policy',
          ring: 3,
          group: 'security',
          status: 'active',
          path: 'c:/Users/alesh/jev-workspace/capability_policy.json',
          tags: ['security', 'air-gap', 'zones'],
          requires: ['execution', 'source-governance'],
          summary: 'Enforces loopback-only socket guards and least-privilege capability manifests across all 5 workspace agent groups.',
          content: '5 Enforced Agent Zones: delivery_offline_discovery_and_worker, delivery_offline_reconciliation_harness, gtm_research_batch_and_dispatcher, gtm_smtp_alert_relay, hud_operator_interface. Default unlisted plugin state: OFF.'
        }
      ],
      links: []
    },
    inbox_outbox: {
      inbox: [
        {
          id: 'offline:initial:job-strict-01',
          channel: 'OFFLINE_SNAPSHOT_DIODE',
          title: 'Ledger Reconciliation Snapshot: job-strict-01',
          state: 'completed',
          reference: 'd90a777c4b487eab',
          timestamp: '2026-10-17T11:29:09.870Z',
          jev_noul_urgent: '0.14',
          outcome_badge: 'done',
          linked_node: 'inbox-offline-snapshot',
          detail: 'Exported via offline_observer.py (?mode=ro). Zero-loss batch invariant: 12 == 10 + 1 + 1 (PASS).'
        },
        {
          id: 'offline:initial:job-daemon-01',
          channel: 'OFFLINE_SNAPSHOT_DIODE',
          title: 'Risk Extraction Snapshot: job-daemon-01',
          state: 'completed',
          reference: '0eeeb9d284040fff',
          timestamp: '2026-10-17T11:29:09.870Z',
          jev_noul_urgent: '0.22',
          outcome_badge: 'done',
          linked_node: 'inbox-offline-snapshot',
          detail: 'ClientRiskProfile validated with StrictStr money fields. Annual exposure string: $826,920.00.'
        },
        {
          id: 'audio:client_discovery_call.wav',
          channel: 'INBOX_AUDIO_DROP',
          title: 'Discovery Audio Drop: client_discovery_call.wav',
          state: 'transcribed_verified',
          reference: 'delivery-offline/inbox-audio',
          timestamp: '2026-10-18T05:35:00.000Z',
          jev_noul_urgent: '0.68',
          outcome_badge: 'done',
          linked_node: 'mark-lvi-engine',
          detail: 'Processed by faster-whisper CPU pipeline -> step6_discovery_pipeline.py -> SOW_Keystone_Precision_Machining.md.'
        },
        {
          id: 'quar:row-4-malformed',
          channel: 'QUARANTINE_INSPECTOR',
          title: 'Adversarial CSV Quarantine: Row 4 (INV-1004)',
          state: 'quarantined',
          reference: 'adversarial_fixture.csv',
          timestamp: '2026-10-22T07:12:00.000Z',
          jev_noul_urgent: '0.89',
          outcome_badge: 'ask',
          linked_node: 'Risk Guard Role',
          detail: 'Rejected negative/malformed StrictStr amount "-450.00" at boundary. Preserved verbatim for human audit.'
        }
      ],
      outbox: [
        {
          id: 'gtm_001',
          channel: 'GTM_HUMAN_REVIEW_OUTBOX',
          title: 'Cambridge Specialty Company — Reconciliation bottlenecks',
          state: 'needs_review',
          requires_review: true,
          recipient: 'ap-ar@cambridgespecialty.com',
          vertical: 'Precision Manufacturing / B2B',
          outcome_badge: 'ask',
          linked_node: 'outbox-gtm-queue',
          detail: 'Subject: Reconciliation bottlenecks at Cambridge Specialty Company (JobBOSS balance checks and monthly GL reconciliations).'
        },
        {
          id: 'gtm_bbbf06f3',
          channel: 'GTM_HUMAN_REVIEW_OUTBOX',
          title: 'Apex Thermal Solutions — OEM parts credit & work order match',
          state: 'needs_review',
          requires_review: true,
          recipient: 'ops-billing@apexthermalsolutions.com',
          vertical: 'Commercial Refrigeration / HVAC',
          outcome_badge: 'ask',
          linked_node: 'outbox-gtm-queue',
          detail: '3-way match field technician part requisitions, vendor counter receipts, and OEM credit statements in ServiceTitan.'
        },
        {
          id: 'gtm_d0db6559',
          channel: 'GTM_HUMAN_REVIEW_OUTBOX',
          title: 'ColdChain Mechanical — Jonas job costing vs. supply house',
          state: 'approved',
          requires_review: false,
          recipient: 'ap@coldchainmechanical.com',
          vertical: 'Commercial Refrigeration / HVAC',
          outcome_badge: 'done',
          linked_node: 'outbox-gtm-queue',
          detail: 'Approved with content-hash lock. Isolates unbilled emergency WIP before monthly financial review.'
        },
        {
          id: 'evt-0001',
          channel: 'METADATA_DIODE_OUTBOX',
          title: 'Diode Event evt-0001: job-hud-1792373601 (running -> validated)',
          state: 'pending_relay',
          requires_review: true,
          recipient: 'smtp_tls_relay',
          vertical: 'Air-Gap Diode',
          outcome_badge: 'unverified',
          linked_node: 'outbox-metadata-diode',
          detail: 'Sanitized metadata event waiting in notification-outbox/metadata_outbox.json. Zero PII or currency strings.'
        },
        {
          id: 'evt-0003',
          channel: 'METADATA_DIODE_OUTBOX',
          title: 'Diode Event evt-0003: job-hud-1792373601 (approved -> completed)',
          state: 'pending_relay',
          requires_review: false,
          recipient: 'smtp_tls_relay',
          vertical: 'Air-Gap Diode',
          outcome_badge: 'unverified',
          linked_node: 'outbox-metadata-diode',
          detail: 'Ready for isolated SMTP TLS 465 relay flush. If SMTP is unconfigured, remains queued (never falsely reported as sent).'
        }
      ]
    },
    agents_workflows: {
      default_unlisted_plugin_state: 'OFF',
      workspace_agents: [
        {
          id: 'delivery_offline_discovery_and_worker',
          label: 'Offline Discovery & SOW Worker',
          zone: 'delivery-offline',
          network_policy: 'loopback_only_127_0_0_1',
          status: 'ONLINE_ENFORCED',
          linked_node: 'local-models',
          scripts: ['worker_daemon.py', 'step6_discovery_pipeline.py', 'inference_adapter.py', 'job_ledger.py'],
          enabled_capabilities: ['local_llm_loopback_8080', 'sqlite_ledger_rw', 'decimal_deterministic_math', 'pydantic_strict_contracts', 'jinja2_strict_sow_engine', 'diode_sanitized_writer'],
          disabled_capabilities: ['outbound_internet_http', 'smtp_client_socket', 'public_web_scraper', 'crm_external_sync', 'unvalidated_float_math']
        },
        {
          id: 'delivery_offline_reconciliation_harness',
          label: 'Zero-Loss Reconciliation Harness',
          zone: 'delivery-offline',
          network_policy: 'zero_network',
          status: 'ONLINE_ENFORCED',
          linked_node: 'verification',
          scripts: ['reconciliation_harness.py', 'data_contracts.py'],
          enabled_capabilities: ['csv_adversarial_ingestion', 'zero_loss_invariant_check', 'decimal_deterministic_math', 'pydantic_strict_contracts'],
          disabled_capabilities: ['local_llm_loopback_8080', 'outbound_internet_http', 'smtp_client_socket', 'external_file_upload']
        },
        {
          id: 'gtm_research_batch_and_dispatcher',
          label: 'GTM Research & Staging Gate',
          zone: 'gtm-research',
          network_policy: 'gtm_isolated',
          status: 'ONLINE_ENFORCED',
          linked_node: 'outbox-gtm-queue',
          scripts: ['gtm_dispatcher.py', 'batch_processor.py', 'expand_gtm_batches.py', 'review_staged_outreach.py'],
          enabled_capabilities: ['public_prospect_intelligence', 'pydantic_outreach_staging', 'human_review_gate_needs_review', 'diode_sanitized_writer'],
          disabled_capabilities: ['offline_job_ledger_db_access', 'raw_client_transcript_reader', 'autonomous_unapproved_email_send']
        },
        {
          id: 'gtm_smtp_alert_relay',
          label: 'Isolated SMTP Metadata Relay',
          zone: 'gtm-research',
          network_policy: 'smtp_tls_only',
          status: 'STANDBY_GUARDED',
          linked_node: 'outbox-metadata-diode',
          scripts: ['smtp_alert_relay.py'],
          enabled_capabilities: ['diode_outbox_reader', 'regex_pii_and_currency_scrubber', 'smtp_gmail_tls_465'],
          disabled_capabilities: ['offline_job_ledger_db_access', 'raw_client_transcript_reader', 'local_llm_loopback_8080']
        },
        {
          id: 'hud_operator_interface',
          label: 'HUD Command & Omnibus Broker',
          zone: 'hud-interface',
          network_policy: 'loopback_only_127_0_0_1',
          status: 'ONLINE_ENFORCED',
          linked_node: 'core.md',
          scripts: ['hud_server.py', 'hud/server.py', 'hud/omnibus.py'],
          enabled_capabilities: ['http_loopback_server_5050', 'sqlite_ledger_readonly_mode_ro', 'module_c_operator_review_gate', 'omniscient_index_broker'],
          disabled_capabilities: ['outbound_internet_http', 'smtp_client_socket', 'sqlite_direct_unvalidated_write']
        }
      ],
      jev_ten_levels: [
        { level: 1, name: 'Single Decisions', primitive: 'noul', hook: 'Code Gate', example: 'Prompt injection & urgency gate (0..1 threshold)' },
        { level: 2, name: 'Multiple Choice', primitive: 'choice', hook: 'Code Fan-out', example: 'Support triage & B2B sponsor qualification' },
        { level: 3, name: 'Composite Scoring', primitive: 'score', hook: 'Weighted Code', example: 'Severity (0.6) + Frustration (0.3) + Quality (0.1)' },
        { level: 4, name: 'Confidence Gating', primitive: 'choice+conf', hook: 'Human Escalation', example: '<0.50 human | 0.50-0.90 confirm | >0.90 auto' },
        { level: 5, name: 'Intent & Model Routing', primitive: 'choice+score', hook: 'Harness Router', example: 'Route to script, fast agent, local Qwen3, or human' },
        { level: 6, name: 'Guardrail Hooks', primitive: 'noul+choice', hook: 'tool_call / result', example: 'Bash irreversible gate + untrusted result screen' },
        { level: 7, name: 'Should I Compact', primitive: '4x noul/score', hook: 'turn_end', example: 'switched_gears + at_boundary + live_from cut point' },
        { level: 8, name: 'Cheap File Reads', primitive: 'ask_jev_file_*', hook: 'Agent Tool', example: 'Judge 9k tokens for $0.00049 without context bloat' },
        { level: 9, name: 'Files at Scale', primitive: 'ask_jev_files', hook: 'Parallel Glob', example: 'Scout 255 files in parallel + pick_first_file' },
        { level: 10, name: 'Agentic Jev', primitive: 'ask_jev', hook: 'Autonomous', example: 'Agent writes state + paths + command + question JSON' }
      ],
      mark_lvi_stack: {
        hearing_stt: { provider: 'faster-whisper (CPU)', warm_latency: '1.16s', detail: '0.1s silence warm-up kernel; language-following voice code' },
        thinking_llm: { provider: 'Hermes / Qwen3:4b (127.0.0.1:8080)', budget: '12 tools / 11,615 chars', detail: 'Streaming <think> tag stripper + duplicate tool-call floor' },
        speaking_tts: { provider: 'Piper Neural TTS (CPU)', speed: '15x realtime (0.34s / 5.15s)', detail: '52 languages; auto-switches voice to match Whisper input' }
      }
    },
    jev_trading_state: {
      rung: 'RUN',
      action: 'BUY',
      mode: 'dry',
      symbol: 'BTC/USD (Paper Default - Explicit Opt-in Required)',
      max_position_usd: '$50.00',
      max_loss_usd: '$25.00',
      judgments: {
        regime: 'trending',
        direction: 'up',
        toxic_flow: 'low',
        liquidity_stress: 'low',
        quote_environment: 'clean',
        inventory_pressure: 'neutral',
        execution_health: 'healthy'
      }
    }
  };

  // Populate links from node.requires
  (function buildLinks() {
    const nodes = DEFAULT_OMNIBUS.second_brain.nodes;
    const set = new Set(nodes.map(n => n.id));
    const links = [];
    nodes.forEach(n => {
      (n.requires || []).forEach(req => {
        if (set.has(req)) links.push({ source: req, target: n.id });
      });
    });
    DEFAULT_OMNIBUS.second_brain.links = links;
  })();

  // Undo Stack (Mark LVI `core/undo.py` closure pattern)
  const undoStack = [];
  function pushUndo(description, undoFn) {
    undoStack.push({
      id: 'undo-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
      description,
      timestamp: new Date().toLocaleTimeString(),
      undoFn
    });
  }

  function performUndo() {
    if (undoStack.length === 0) {
      return { outcome: 'failed', message: 'Undo stack is empty — no reversible actions recorded yet.' };
    }
    const item = undoStack.pop();
    try {
      item.undoFn();
      return { outcome: 'done', message: `Reversed last action: ${item.description}` };
    } catch (err) {
      return { outcome: 'failed', message: `Undo failed: ${err.message}` };
    }
  }

  // Deterministic JEV System-One Evaluator (Client + Server twin)
  function evaluateJevSystemOne(stateObj, questionsObj) {
    const blob = JSON.stringify(stateObj || {}).toLowerCase();
    const answers = {};
    Object.keys(questionsObj || {}).forEach(qid => {
      const q = questionsObj[qid];
      const qtype = q.type || 'noul';
      const prompt = String(q.question || '').toLowerCase();
      if (qtype === 'noul') {
        let val = 0.14;
        if (qid.includes('injection') || prompt.includes('manipulate') || prompt.includes('instruct')) {
          const terms = ['ignore previous', 'system prompt', 'rm -rf', 'drop table', 'override', 'bypass', 'heredoc'];
          const hits = terms.filter(t => blob.includes(t)).length;
          val = Math.min(0.99, +(0.03 + hits * 0.44).toFixed(2));
        } else if (qid.includes('urgent') || prompt.includes('urgent')) {
          const terms = ['broken', 'down', 'losing revenue', 'emergency', 'breach', 'quarantined', 'critical', 'overtime'];
          const hits = terms.filter(t => blob.includes(t)).length;
          val = Math.min(0.98, +(0.16 + hits * 0.27).toFixed(2));
        } else if (qid.includes('switch') || prompt.includes('switched')) {
          val = blob.includes('switch') || blob.includes('new task') ? 0.96 : 0.18;
        } else {
          val = blob.length > 60 ? 0.84 : 0.42;
        }
        answers[qid] = { type: 'noul', noul: val };
      } else if (qtype === 'choice') {
        const opts = q.options && q.options.length ? q.options : ['healthy', 'degraded', 'other'];
        let picked = opts[0];
        let conf = 0.91;
        opts.forEach(o => {
          if (blob.includes(o.toLowerCase().replace(/_/g, ' ')) || blob.includes(o.toLowerCase())) {
            picked = o;
            conf = 0.95;
          }
        });
        if (blob.includes('rm -rf') && opts.includes('irreversible')) {
          picked = 'irreversible';
          conf = blob.includes('node_modules') ? 0.35 : 0.99;
        }
        const gateAction = conf < 0.50 ? 'ASK_HUMAN (<0.50 floor)' : (conf < 0.90 ? 'CONFIRM_GATE (0.50..0.90)' : 'AUTO_VERIFIED (>0.90)');
        answers[qid] = { type: 'choice', choice: picked, confidence: conf, gate: gateAction };
      } else if (qtype === 'score') {
        const levels = q.levels && q.levels.length ? q.levels : ['low', 'moderate', 'high', 'critical'];
        let idx = 0;
        if (['critical', 'breach', 'kill', 'losing revenue'].some(k => blob.includes(k))) idx = levels.length - 1;
        else if (['quarantined', 'degraded', 'warning', 'stale', 'overtime'].some(k => blob.includes(k))) idx = Math.max(1, Math.floor(levels.length / 2));
        const score = +((idx + 0.22) / levels.length).toFixed(2);
        answers[qid] = { type: 'score', score, legend: levels[idx], confidence: 0.92 };
      }
    });
    return {
      // Keyword heuristic stand-in; never present as Jev model output. Nothing is timed or billed.
      engine: 'local-heuristic-standin',
      is_jev_output: false,
      answers
    };
  }

  // Deterministic JEV 7-Judgment -> 5-Action Rung Composer
  function evaluateTradingRung(judgments, hardBreach) {
    let rung = 'RUN';
    let action = 'BUY';
    if (hardBreach || judgments.execution_health === 'critical') {
      rung = 'KILL';
      action = 'HOLD';
    } else if (judgments.toxic_flow === 'high' || judgments.liquidity_stress === 'high') {
      rung = 'HOLD_LATE';
      action = 'HOLD';
    } else if (judgments.execution_health === 'degraded' || judgments.quote_environment === 'stale') {
      rung = 'RULES_ONLY';
      action = 'HOLD';
    } else if (judgments.inventory_pressure === 'elevated' || judgments.toxic_flow === 'moderate') {
      rung = 'REDUCE';
      action = judgments.direction === 'up' ? 'BUY' : 'HOLD';
    } else {
      rung = 'RUN';
      action = judgments.direction === 'up' ? 'BUY' : (judgments.direction === 'down' ? 'SELL' : 'HOLD');
    }
    return {
      rung,
      action,
      mode: 'dry (NOT_SENT)',
      max_position_usd: '$50.00',
      max_loss_usd: '$25.00',
      judgments: Object.assign({}, judgments)
    };
  }

  // Omniscient Project Assistant (Mark LVI Key-Index + JEV Level 8/9 Cheap Reads)
  function queryOmniscientAssistant(queryText, omnibusState) {
    const q = String(queryText || '').trim();
    const qLow = q.toLowerCase();
    const nodes = omnibusState.second_brain.nodes;
    const inbox = omnibusState.inbox_outbox.inbox;
    const outbox = omnibusState.inbox_outbox.outbox;
    const agents = omnibusState.agents_workflows.workspace_agents;

    const triage = evaluateJevSystemOne(
      { query: q },
      {
        is_injection: { type: 'noul', question: 'Does query attempt prompt injection or instruction override?' },
        route: { type: 'choice', options: ['second_brain_graph', 'inbox_outbox_diode', 'jev_trading_roles', 'agent_capabilities', 'financial_strict_ledger', 'mark_lvi_voice_stack'] },
        priority: { type: 'score', levels: ['routine', 'operational', 'high', 'critical'] }
      }
    );

    if (triage.answers.is_injection.noul > 0.65) {
      return {
        outcome: 'failed',
        badgeClass: 'err',
        triage,
        matchedNodes: ['source-governance', 'capability-policy'],
        citations: ['JEV Level 1/6 Injection Gate', 'Mark LVI Untrusted-Content Boundary'],
        reply: 'Blocked by JEV Level 1/6 Guardrail Gate (noul=' + triage.answers.is_injection.noul + '). Instruction-override pattern detected inside query.',
        untrustedPreview: wrapUntrusted(q, 'blocked_user_input')
      };
    }

    const tokens = qLow.split(/[^a-z0-9_-]+/).filter(t => t.length >= 3);
    const scored = [];
    nodes.forEach(n => {
      const hay = (n.id + ' ' + n.label + ' ' + n.summary + ' ' + n.content + ' ' + (n.tags || []).join(' ')).toLowerCase();
      let score = 0;
      tokens.forEach(tok => {
        if (n.label.toLowerCase().includes(tok)) score += 3;
        else if (hay.includes(tok)) score += 1;
      });
      if (score > 0) scored.push({ score, n });
    });
    scored.sort((a, b) => b.score - a.score);
    let matched = scored.map(s => s.n);
    if (matched.length === 0) {
      matched = [nodes[0], nodes[6], nodes[11], nodes[21]];
    }

    const lines = [];
    lines.push(`[Local keyword index: searched ${nodes.length} vault nodes + ${inbox.length + outbox.length} diode items. Triage by heuristic stand-in, not Jev output.]`);

    if (tokens.some(t => ['money', 'financial', 'ledger', 'sow', 'risk', 'savings', 'invoice', 'quarantine', 'decimal'].includes(t))) {
      const fin = omnibusState.financial_strict_strings;
      lines.push(`• Financial Vault (StrictStr Verified): Annual Risk Exposure = ${fin.annual_risk_exposure_usd} | Projected 85% Savings = ${fin.projected_savings_usd} | Canary = ${fin.precision_canary_usd} | Invariant = ${fin.ledger_invariant_formula}.`);
    }
    if (tokens.some(t => ['inbox', 'outbox', 'diode', 'gtm', 'cambridge', 'apex', 'coldchain', 'vetpowered', 'email', 'smtp'].includes(t))) {
      const needsRev = outbox.filter(o => o.requires_review).length;
      lines.push(`• Diode Inbox/Outbox: ${inbox.length} Inbox items (${inbox.map(i => i.id).join(', ')}) | ${outbox.length} Outbox items (${needsRev} awaiting human review gate).`);
    }
    if (tokens.some(t => ['agent', 'agents', 'workflow', 'zone', 'capability', 'hermes', 'plugin', 'mark', 'lvi', 'whisper', 'piper'].includes(t))) {
      lines.push(`• Agent & Engine Matrix: ${agents.length} least-privilege zones enforced (unlisted plugins=${omnibusState.agents_workflows.default_unlisted_plugin_state}). Mark LVI Stack: ${omnibusState.agents_workflows.mark_lvi_stack.hearing_stt.provider} -> ${omnibusState.agents_workflows.mark_lvi_stack.thinking_llm.provider} -> ${omnibusState.agents_workflows.mark_lvi_stack.speaking_tts.provider}.`);
    }
    if (tokens.some(t => ['jev', 'rung', 'trading', 'role', 'roles', 'noul', 'choice', 'score', 'obsidian', 'ring', 'brain', 'budget', 'budgeting'].includes(t)) || lines.length === 1) {
      const tr = omnibusState.jev_trading_state;
      lines.push(`• JEV System & Second Brain: Active Rung = ${tr.rung} (Action: ${tr.action}, Mode: ${tr.mode}, Caps: ${tr.max_position_usd} pos / ${tr.max_loss_usd} loss). Optional Budgeting module is explicitly DISABLED per manifest.json.`);
    }

    matched.slice(0, 3).forEach(n => {
      lines.push(`• [Ring ${n.ring} · ${n.label}] (${n.status.toUpperCase()}): ${n.summary}`);
    });

    return {
      outcome: 'done',
      badgeClass: 'ok',
      triage,
      matchedNodes: matched.slice(0, 6).map(n => n.id),
      citations: matched.slice(0, 4).map(n => `${n.label} (${n.path})`),
      reply: lines.join('\n'),
      untrustedPreview: wrapUntrusted(matched.slice(0, 2).map(n => `${n.id}:\n${n.content}`).join('\n\n'), 'second_brain_vault_read')
    };
  }

  // =========================================================================
  // OBSIDIAN GRAPH RENDERER (Supports 2D Concentric Rings + Minimal 3D Orbital Rings + 3D Fibonacci Sphere)
  // =========================================================================
  function createObsidianGraphController(canvasEl, options) {
    const opts = Object.assign({
      mode: 'ring2d', // 'ring2d' | 'orbital3d' | 'sphere3d'
      onSelectNode: function () {},
      ringColors: ['#38bdf8', '#a78bfa', '#10b981', '#f59e0b']
    }, options || {});

    const ctx = canvasEl.getContext('2d');
    let nodes = [];
    let links = [];
    let selectedId = 'core.md';
    let highlightedIds = new Set(['core.md']);
    let hoveredId = null;
    let filterRing = 'all';
    let searchQuery = '';

    // 3D camera state
    let rotY = 0.42;
    let rotX = 0.34;
    let zoom = 1.0;
    let autoRotate = true;
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let screenPositions = [];

    function setData(secondBrainData) {
      const rawNodes = secondBrainData.nodes || [];
      links = secondBrainData.links || [];
      const ringBuckets = { 0: [], 1: [], 2: [], 3: [] };
      rawNodes.forEach(n => {
        if (!ringBuckets[n.ring]) ringBuckets[n.ring] = [];
        ringBuckets[n.ring].push(n);
      });

      const total = rawNodes.length;
      nodes = rawNodes.map((n, globalIdx) => {
        const bucket = ringBuckets[n.ring] || [n];
        const idxInRing = bucket.indexOf(n);
        const angle = (idxInRing / Math.max(1, bucket.length)) * Math.PI * 2 - Math.PI / 2;
        // Fibonacci sphere coords for sphere3d mode
        const phi = Math.acos(1 - 2 * (globalIdx + 0.5) / total);
        const theta = Math.PI * (1 + Math.sqrt(5)) * (globalIdx + 0.5);
        return Object.assign({}, n, {
          angle,
          idxInRing,
          ringCount: bucket.length,
          fibPhi: phi,
          fibTheta: theta
        });
      });
      selectNode(selectedId, false);
    }

    function selectNode(nodeId, triggerCallback) {
      const target = nodes.find(n => n.id === nodeId) || nodes[0];
      if (!target) return;
      selectedId = target.id;
      highlightedIds = new Set([target.id]);
      links.forEach(l => {
        if (l.source === target.id) highlightedIds.add(l.target);
        if (l.target === target.id) highlightedIds.add(l.source);
      });
      if (triggerCallback !== false && opts.onSelectNode) {
        opts.onSelectNode(target, Array.from(highlightedIds));
      }
    }

    function highlightSet(idArray) {
      highlightedIds = new Set(idArray || []);
      if (idArray && idArray.length > 0) {
        selectedId = idArray[0];
        const target = nodes.find(n => n.id === selectedId);
        if (target && opts.onSelectNode) opts.onSelectNode(target, Array.from(highlightedIds));
      }
    }

    function resize() {
      const rect = canvasEl.parentElement.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvasEl.width = Math.max(300, Math.floor(rect.width * dpr));
      canvasEl.height = Math.max(260, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function projectNode(n, width, height, timeSec) {
      const cx = width / 2;
      const cy = height / 2;
      const minDim = Math.min(width, height) * zoom;
      const radii = [0, minDim * 0.16, minDim * 0.31, minDim * 0.44];
      const r = radii[n.ring] !== undefined ? radii[n.ring] : minDim * 0.44;

      if (opts.mode === 'ring2d') {
        const drift = n.ring === 0 ? 0 : timeSec * 0.04 * (n.ring % 2 === 1 ? 1 : -0.7);
        const a = n.angle + drift;
        return {
          x: cx + Math.cos(a) * r,
          y: cy + Math.sin(a) * r,
          z: 0,
          scale: 1
        };
      }

      // 3D modes: 'orbital3d' or 'sphere3d'
      let x3 = 0, y3 = 0, z3 = 0;
      if (opts.mode === 'orbital3d') {
        const a = n.angle + (n.ring === 0 ? 0 : timeSec * 0.08 * (n.ring === 1 ? 1 : (n.ring === 2 ? -0.7 : 0.5)));
        const tilt = n.ring === 1 ? 0.38 : (n.ring === 2 ? -0.32 : (n.ring === 3 ? 0.18 : 0));
        x3 = Math.cos(a) * r;
        z3 = Math.sin(a) * r * Math.cos(tilt);
        y3 = Math.sin(a) * r * Math.sin(tilt);
      } else {
        // sphere3d
        const sr = n.ring === 0 ? 0 : minDim * 0.38;
        x3 = sr * Math.sin(n.fibPhi) * Math.cos(n.fibTheta);
        y3 = sr * Math.cos(n.fibPhi);
        z3 = sr * Math.sin(n.fibPhi) * Math.sin(n.fibTheta);
      }

      // Rotate around Y then X
      const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
      const x1 = x3 * cosY - z3 * sinY;
      const z1 = z3 * cosY + x3 * sinY;

      const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
      const y2 = y3 * cosX - z1 * sinX;
      const z2 = z1 * cosX + y3 * sinX;

      const fov = 520;
      const scale = fov / Math.max(160, fov + z2);
      return {
        x: cx + x1 * scale,
        y: cy + y2 * scale,
        z: z2,
        scale
      };
    }

    function render(ts) {
      const timeSec = (ts || 0) * 0.001;
      if (autoRotate && !dragging && opts.mode !== 'ring2d') {
        rotY += 0.0032;
      }

      const dpr = window.devicePixelRatio || 1;
      const width = canvasEl.width / dpr;
      const height = canvasEl.height / dpr;
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const minDim = Math.min(width, height) * zoom;
      const radii = [0, minDim * 0.16, minDim * 0.31, minDim * 0.44];

      // Draw Concentric Guide Rings
      for (let rIdx = 1; rIdx <= 3; rIdx++) {
        if (filterRing !== 'all' && Number(filterRing) !== rIdx) continue;
        ctx.save();
        ctx.strokeStyle = opts.ringColors[rIdx] || '#38bdf8';
        ctx.globalAlpha = opts.mode === 'ring2d' ? 0.18 : 0.11;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 6]);
        ctx.beginPath();
        if (opts.mode === 'ring2d') {
          ctx.arc(cx, cy, radii[rIdx], 0, Math.PI * 2);
        } else {
          ctx.ellipse(cx, cy, radii[rIdx], radii[rIdx] * Math.max(0.28, Math.abs(Math.sin(rotX + 0.35))), 0, 0, Math.PI * 2);
        }
        ctx.stroke();
        ctx.restore();
      }

      // Compute projections
      const posMap = {};
      screenPositions = nodes.map(n => {
        const p = projectNode(n, width, height, timeSec);
        const visibleByRing = filterRing === 'all' || Number(filterRing) === n.ring || n.ring === 0;
        const matchesSearch = !searchQuery || (n.label + ' ' + n.id + ' ' + n.tags.join(' ')).toLowerCase().includes(searchQuery);
        const item = { node: n, x: p.x, y: p.y, z: p.z, scale: p.scale, visible: visibleByRing && matchesSearch };
        posMap[n.id] = item;
        return item;
      });

      // Draw Dependency Links
      links.forEach(l => {
        const s = posMap[l.source];
        const t = posMap[l.target];
        if (!s || !t || !s.visible || !t.visible) return;
        const isActive = (s.node.id === selectedId || t.node.id === selectedId);
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = isActive ? '#38bdf8' : 'rgba(148, 163, 184, 0.22)';
        ctx.lineWidth = isActive ? 1.8 : 0.9;
        ctx.stroke();
        ctx.restore();
      });

      // Depth-sort nodes back-to-front
      const sorted = screenPositions.slice().sort((a, b) => b.z - a.z);

      sorted.forEach(item => {
        if (!item.visible) return;
        const n = item.node;
        const isSelected = n.id === selectedId;
        const isHovered = n.id === hoveredId;
        const isHighlighted = highlightedIds.has(n.id);
        const baseColor = n.status === 'disabled' ? '#64748b' : (opts.ringColors[n.ring] || '#38bdf8');
        const baseRadius = (n.ring === 0 ? 11 : (n.ring === 1 ? 7.5 : 6.2)) * item.scale;

        ctx.save();
        ctx.globalAlpha = isHighlighted ? 1.0 : 0.42;

        // Outer halo for selected/hovered or Ring 0
        if (isSelected || isHovered || n.ring === 0) {
          ctx.beginPath();
          ctx.arc(item.x, item.y, baseRadius + 5, 0, Math.PI * 2);
          ctx.strokeStyle = isSelected ? '#f8fafc' : baseColor;
          ctx.lineWidth = isSelected ? 2 : 1.2;
          ctx.stroke();
        }

        // Node circle (minimal ring aesthetic)
        ctx.beginPath();
        ctx.arc(item.x, item.y, baseRadius, 0, Math.PI * 2);
        ctx.fillStyle = isSelected ? baseColor : '#0b1120';
        ctx.fill();
        ctx.lineWidth = 2.2;
        ctx.strokeStyle = baseColor;
        ctx.stroke();

        // Label
        ctx.font = `${isSelected ? '600' : '500'} ${Math.max(10, Math.round(11 * item.scale))}px ui-monospace, SFMono-Regular, Consolas, monospace`;
        ctx.fillStyle = isSelected ? '#ffffff' : (isHighlighted ? '#e2e8f0' : '#94a3b8');
        ctx.textAlign = 'center';
        ctx.fillText(n.label, item.x, item.y + baseRadius + 13);
        ctx.restore();
      });

      requestAnimationFrame(render);
    }

    // Pointer Interactions
    canvasEl.addEventListener('mousedown', e => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });

    window.addEventListener('mouseup', () => { dragging = false; });

    canvasEl.addEventListener('mousemove', e => {
      const rect = canvasEl.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (dragging && opts.mode !== 'ring2d') {
        const dx = e.clientX - lastX;
        const dy = e.clientY - lastY;
        rotY += dx * 0.007;
        rotX = Math.max(-1.2, Math.min(1.2, rotX + dy * 0.007));
        lastX = e.clientX;
        lastY = e.clientY;
        return;
      }

      let found = null;
      for (let i = 0; i < screenPositions.length; i++) {
        const p = screenPositions[i];
        if (!p.visible) continue;
        const dist = Math.hypot(mx - p.x, my - p.y);
        if (dist <= 16) {
          found = p.node.id;
          break;
        }
      }
      hoveredId = found;
      canvasEl.style.cursor = found ? 'pointer' : (opts.mode === 'ring2d' ? 'default' : 'grab');
    });

    canvasEl.addEventListener('click', e => {
      const rect = canvasEl.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      for (let i = 0; i < screenPositions.length; i++) {
        const p = screenPositions[i];
        if (!p.visible) continue;
        if (Math.hypot(mx - p.x, my - p.y) <= 18) {
          selectNode(p.node.id, true);
          break;
        }
      }
    });

    canvasEl.addEventListener('wheel', e => {
      e.preventDefault();
      zoom = Math.max(0.65, Math.min(1.55, zoom + (e.deltaY < 0 ? 0.08 : -0.08)));
    }, { passive: false });

    window.addEventListener('resize', resize);
    setTimeout(() => {
      resize();
      requestAnimationFrame(render);
    }, 20);

    return {
      setData,
      selectNode,
      highlightSet,
      setMode(newMode) { opts.mode = newMode; },
      getMode() { return opts.mode; },
      setFilterRing(ringVal) { filterRing = ringVal; },
      setSearch(q) { searchQuery = String(q || '').toLowerCase().trim(); },
      toggleAutoRotate() { autoRotate = !autoRotate; return autoRotate; },
      resetView() { rotY = 0.42; rotX = 0.34; zoom = 1.0; filterRing = 'all'; }
    };
  }

  global.JEVOmnibus = {
    DEFAULT_OMNIBUS,
    wrapUntrusted,
    pushUndo,
    performUndo,
    getUndoStack: () => undoStack.slice(),
    evaluateJevSystemOne,
    evaluateTradingRung,
    queryOmniscientAssistant,
    createObsidianGraphController
  };
})(window);
