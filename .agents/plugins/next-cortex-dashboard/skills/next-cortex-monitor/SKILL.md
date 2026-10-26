---
name: next-cortex-monitor
description: "Monitor Antigravity IDE credits, model token quotas, and automated task execution history. ACTIVATE this skill when auditing credit consumption, quota countdowns, or checking automated agent task approval states."
---

# Next Cortex Monitor Skill

## Overview
The Next Cortex Monitor skill provides real-time oversight of Antigravity IDE resource usage, token quotas, remaining credits, and background automated agent task approvals.

## Endpoints & Data Model

### 1. Credits & Model Quota (`GET /api/cortex/credits`)
Returns the current credit allocation, consumption metrics, and quota reset timer:
```json
{
  "total_budget": 100000,
  "credits_remaining": 94820,
  "credits_consumed": 5180,
  "usage_percent": 5.18,
  "reset_countdown_seconds": 43200,
  "reset_time_utc": "2026-10-26T12:00:00Z",
  "active_model": "qwen3:4b (Local / Unmetered)",
  "burn_rate_credits_per_min": 12.4
}
```

### 2. Automated Tasks & Auto-Accept Agent (`GET /api/cortex/tasks`)
Inspects automated agent actions, approval states, and execution status:
```json
{
  "auto_accept_enabled": true,
  "total_automated_tasks": 42,
  "pending_review": 1,
  "recent_tasks": [
    {
      "task_id": "auto-task-091a",
      "command": "reconciliation",
      "status": "auto_approved",
      "duration_ms": 48.2,
      "timestamp_utc": "2026-10-26T01:30:00Z"
    }
  ]
}
```

### 3. Toggling Auto-Accept (`POST /api/cortex/auto-accept`)
Enables or disables hands-free approval for safe operator actions:
```json
{
  "enabled": true
}
```

## Operator Runbook
1. Query `GET /api/cortex/credits` to verify remaining credits prior to large agent runs.
2. If credits fall below 10%, review local inference fallback (`HERMES_ENDPOINT=http://127.0.0.1:8080/v1/chat/completions`).
3. Toggle auto-accept via `POST /api/cortex/auto-accept` when conducting autonomous testing.
