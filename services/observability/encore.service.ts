import { api } from "encore.dev/api";
import { Service } from "encore.dev/service";

export default new Service("observability");

export interface EncoreObservabilityMetrics {
  service_name: string;
  encore_framework_version: string;
  uptime_seconds: number;
  total_requests: number;
  active_spans: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  error_count: number;
  error_rate_percent: number;
  recent_traces_count: number;
  timestamp_utc: string;
}

export interface EncoreTracesResponse {
  status: string;
  traces: {
    trace_id: string;
    span_id: string;
    parent_span_id?: string;
    service: string;
    name: string;
    method: string;
    duration_ms: number;
    status_code: number;
    attributes: Record<string, any>;
  }[];
}

const HUD_SERVER_BASE = process.env.HUD_SERVER_URL || "http://127.0.0.1:5050";

/**
 * Built-in Observability: Live system monitoring metrics, throughput, and latency percentiles.
 */
export const getObservabilityMetrics = api(
  { expose: true, method: "GET", path: "/api/observability/metrics" },
  async (): Promise<EncoreObservabilityMetrics> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/observability/metrics`);
    return (await res.json()) as EncoreObservabilityMetrics;
  }
);

/**
 * Built-in Observability: Live distributed traces and spans.
 */
export const getObservabilityTraces = api(
  { expose: true, method: "GET", path: "/api/observability/traces" },
  async (): Promise<EncoreTracesResponse> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/observability/traces`);
    return (await res.json()) as EncoreTracesResponse;
  }
);
