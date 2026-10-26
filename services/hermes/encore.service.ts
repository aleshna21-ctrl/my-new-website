import { api } from "encore.dev/api";
import { Service } from "encore.dev/service";

export default new Service("hermes");

export interface GatewayRPCRequest {
  jsonrpc: string;
  id: string | number;
  method: string;
  params: Record<string, any>;
  timestamp_utc?: string;
  idempotency_key?: string;
}

export interface GatewayRPCResponse {
  jsonrpc: string;
  id?: string | number;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: Record<string, any>;
  };
  status: string;
  ack?: {
    ack_id: string;
    sequence_id: number;
  };
  round_trip_ms?: number;
}

export interface HermesTelemetryResponse {
  live_loopback_reachable: boolean;
  live_probe_detail: string;
  last_execution_mode: string;
  is_simulated: boolean;
  last_status: string;
  max_tokens: number;
  max_retries: number;
  model: string;
  endpoint: string;
  probe_running: boolean;
  server_pid: number;
  build_id: string;
}

export interface HermesProbeRequest {
  allow_simulation?: boolean;
}

export interface HermesProbeResponse {
  status: string;
  execution_mode: string;
  is_simulated: boolean;
  attempts: any[];
}

// Proxies to AIOS HUD Server type-safe router
const HUD_SERVER_BASE = process.env.HUD_SERVER_URL || "http://127.0.0.1:5050";

/**
 * Type-safe RPC gateway dispatcher communicating between Hermes Agent and AIOS dashboard.
 */
export const dispatchHermesRPC = api(
  { expose: true, method: "POST", path: "/api/gateway/hermes" },
  async (req: GatewayRPCRequest): Promise<GatewayRPCResponse> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/gateway/hermes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    return (await res.json()) as GatewayRPCResponse;
  }
);

/**
 * Retrieves live Hermes telemetry, model status, and loopback reachability.
 */
export const getHermesTelemetry = api(
  { expose: true, method: "GET", path: "/api/hermes" },
  async (): Promise<HermesTelemetryResponse> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/hermes`);
    return (await res.json()) as HermesTelemetryResponse;
  }
);

/**
 * Executes a type-safe bounded repair probe against the local Hermes model.
 */
export const probeHermesModel = api(
  { expose: true, method: "POST", path: "/api/hermes/probe" },
  async (req: HermesProbeRequest): Promise<HermesProbeResponse> => {
    const res = await fetch(`${HUD_SERVER_BASE}/api/hermes/probe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    return (await res.json()) as HermesProbeResponse;
  }
);
