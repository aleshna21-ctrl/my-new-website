import { api } from "encore.dev/api";
import { Service } from "encore.dev/service";

export default new Service("visualization");

export interface StreamingSeriesPoint {
  ts: string;
  time_epoch: number;
  credits_remaining: number;
  credits_consumed: number;
  burn_rate: number;
  rtt_ms: number;
  jobs_active: number;
  jobs_completed: number;
  throughput_ops_sec: number;
}

export interface StreamingSeriesResponse {
  status: string;
  series: StreamingSeriesPoint[];
  buffer_size: number;
  window_seconds: number;
  trace_id?: string;
}

export interface DAGNode {
  id: string;
  name: string;
  type: string;
  layer: number;
  status?: string;
  scope?: string;
  job_id?: string;
  state?: string;
  attempts?: number;
  updated_at?: string;
}

export interface DAGLink {
  source: string;
  target: string;
  kind: string;
}

export interface CortexHierarchyPayload {
  nodes: DAGNode[];
  links: DAGLink[];
  layers: { layer: number; name: string; tier: string }[];
  summary: {
    total_nodes: number;
    total_links: number;
    jobs_count: number;
    scopes_count: number;
    quarantined_count: number;
  };
  trace_id?: string;
}

export interface SQLiteLedgerPayload {
  db_path: string;
  tables: Record<string, { row_count: number }>;
  jobs: {
    job_id: string;
    scope_id?: string;
    job_type?: string;
    state: string;
    attempt_count: number;
    created_at?: string;
    updated_at?: string;
  }[];
  terminal_events: any[];
  total_jobs: number;
  mode: string;
  timestamp_utc: string;
  trace_id?: string;
}

const HUD_SERVER_BASE = process.env.HUD_SERVER_URL || "http://127.0.0.1:5050";

/**
 * Real-Time Visualization Skill: Rolling 60s circular buffer with dual-axis sync.
 */
export const getStreamingSeries = api(
  { expose: true, method: "GET", path: "/api/cortex/streaming-series" },
  async (): Promise<StreamingSeriesResponse> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/cortex/streaming-series`);
    return (await res.json()) as StreamingSeriesResponse;
  }
);

/**
 * Real-Time Visualization Skill: Multi-level DAG hierarchy layout (Tiers 1 through 4).
 */
export const getHierarchy = api(
  { expose: true, method: "GET", path: "/api/cortex/hierarchy" },
  async (): Promise<CortexHierarchyPayload> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/cortex/hierarchy`);
    return (await res.json()) as CortexHierarchyPayload;
  }
);

/**
 * Real-Time Visualization Skill: Read-only SQLite ledger data diode inspection.
 */
export const getSQLiteLedger = api(
  { expose: true, method: "GET", path: "/api/sqlite/ledger" },
  async (): Promise<SQLiteLedgerPayload> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/sqlite/ledger`);
    return (await res.json()) as SQLiteLedgerPayload;
  }
);
