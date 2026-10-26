#!/usr/bin/env python3
"""
Hermes Local Model Service (127.0.0.1:8080)
Provides an OpenAI-compatible /v1 loopback interface for local Hermes / Qwen3 inference,
bridging requests directly to the local Ollama execution engine (127.0.0.1:11434).
"""
import http.server
import json
import os
import socketserver
import sys
import time
import urllib.request
import urllib.error

HOST = os.environ.get("HERMES_8080_HOST", "0.0.0.0")
PORT = int(os.environ.get("HERMES_8080_PORT", "8080"))
UPSTREAM_BASE = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("HERMES_DEFAULT_MODEL", "qwen3:4b")


class HermesModelHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, data, status=200, ack_id=None, seq_id=None, rtt_ms=None):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Gateway-Timestamp, X-Gateway-Nonce, X-Gateway-Signature, X-Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Cache-Control", "no-cache, no-transform, no-store, private")
        if ack_id:
            self.send_header("X-Gateway-Ack", str(ack_id))
        if seq_id:
            self.send_header("X-Gateway-Seq", str(seq_id))
        if rtt_ms is not None:
            self.send_header("X-Gateway-RTT", str(rtt_ms))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Gateway-Timestamp, X-Gateway-Nonce, X-Gateway-Signature, X-Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        path, _, _ = self.path.partition("?")
        if path in ("/", "/health"):
            self._send_json({
                "status": "ok",
                "service": "hermes-local-model",
                "listening": f"{HOST}:{PORT}",
                "upstream": UPSTREAM_BASE,
                "model": DEFAULT_MODEL,
                "timestamp": time.time()
            })
            return

        if path.startswith("/v1/models"):
            upstream_url = f"{UPSTREAM_BASE}/v1/models"
            try:
                req = urllib.request.Request(upstream_url, method="GET")
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=3.0) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    self._send_json(payload)
                    return
            except Exception as e:
                # Provide standard fallback model listing if upstream is warming up
                self._send_json({
                    "object": "list",
                    "data": [
                        {"id": DEFAULT_MODEL, "object": "model", "owned_by": "hermes-local"},
                        {"id": "qwen3-jev-64k:latest", "object": "model", "owned_by": "hermes-local"}
                    ],
                    "upstream_status": f"unreachable: {e}"
                })
                return

        if path.startswith("/gateway/v1/health"):
            self._send_json({
                "status": "ok",
                "service": "hermes-gateway-daemon",
                "protocol": "JSON-RPC 2.0 / REST Webhook",
                "auth_method": "HMAC-SHA256 (Anti-Replay Nonce + Timestamp)",
                "listening": f"{HOST}:{PORT}",
                "upstream": UPSTREAM_BASE,
                "model": DEFAULT_MODEL,
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
            return

        if path in ("/gateway/v1/sync", "/gateway/v1/feedback"):
            try:
                from hud.gateway import GLOBAL_SYNC_TRACKER, GLOBAL_FEEDBACK_LOOP
                self._send_json({
                    "status": "ok",
                    "service": "hermes-gateway-daemon",
                    "sequence_id": GLOBAL_SYNC_TRACKER.current_seq(),
                    "feedback": GLOBAL_FEEDBACK_LOOP.get_metrics(),
                    "history": GLOBAL_SYNC_TRACKER.get_history(limit=25),
                    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path.startswith("/gateway/v1/crons"):
            try:
                from hud.gateway import load_cron_registry
                self._send_json({"status": "ok", "crons": load_cron_registry()})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        if path.startswith("/gateway/v1/tasks"):
            try:
                from hud.gateway import load_task_history
                self._send_json({"status": "ok", "tasks": load_task_history()})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"error": "Not found", "path": self.path}, 404)

    def do_POST(self):
        start_t = time.monotonic()
        path, _, _ = self.path.partition("?")
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        # --- Gateway Routes with HMAC-SHA256 & Anti-Replay Authentication ---
        if path.startswith("/gateway/v1/"):
            try:
                from hud.gateway import (
                    verify_gateway_request, GatewayAuthError,
                    execute_gateway_rpc, execute_task_command,
                    update_cron_job, trigger_cron_job
                )
            except ImportError as ie:
                self._send_json({"error": f"Gateway module not found: {ie}"}, 500)
                return

            try:
                verify_gateway_request(dict(self.headers), "POST", path, raw_body)
            except GatewayAuthError as gae:
                self._send_json({
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": f"Unauthorized: {gae}"},
                    "status": "unauthorized"
                }, 401)
                return

            try:
                body_json = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                self._send_json({
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": "Parse error: invalid JSON payload"},
                    "status": "error"
                }, 400)
                return

            idemp_key = self.headers.get("X-Idempotency-Key") or body_json.get("idempotency_key")
            if idemp_key and "idempotency_key" not in body_json:
                body_json["idempotency_key"] = idemp_key

            if path == "/gateway/v1/rpc":
                req_id = body_json.get("id")
                method = body_json.get("method", "")
                params = body_json.get("params", {})
                if idemp_key and "idempotency_key" not in params:
                    params["idempotency_key"] = idemp_key

                rpc_res = execute_gateway_rpc(method, params)
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                ack = rpc_res.get("ack")
                out = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": rpc_res.get("result"),
                    "error": rpc_res.get("error"),
                    "status": "error" if rpc_res.get("error") else "ok",
                    "ack": ack,
                    "round_trip_ms": rtt_ms
                }
                status_code = 400 if rpc_res.get("error") else 200
                ack_id = ack.get("ack_id") if ack else None
                seq_id = ack.get("sequence_id") if ack else None
                self._send_json(out, status_code, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            elif path == "/gateway/v1/tasks":
                cmd = body_json.get("command") or body_json.get("cmd", "ping")
                params = body_json.get("params", body_json)
                if idemp_key and "idempotency_key" not in params:
                    params["idempotency_key"] = idemp_key
                res = execute_task_command(cmd, params)
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                ack = res.get("ack")
                ack_id = ack.get("ack_id") if ack else None
                seq_id = ack.get("sequence_id") if ack else None
                self._send_json({"status": "ok", "task": res, "ack": ack, "round_trip_ms": rtt_ms},
                                200, ack_id=ack_id, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            elif path == "/gateway/v1/crons":
                action = body_json.get("action", "update")
                cron_id = body_json.get("id") or body_json.get("cron_id")
                rtt_ms = round((time.monotonic() - start_t) * 1000, 2)
                if action == "trigger":
                    res = trigger_cron_job(cron_id)
                    seq_id = res.get("sequence_id")
                    self._send_json({"status": "ok", "triggered": res, "round_trip_ms": rtt_ms},
                                    200, seq_id=seq_id, rtt_ms=rtt_ms)
                else:
                    res = update_cron_job(cron_id, body_json)
                    seq_id = res.get("sequence_id")
                    self._send_json({"status": "ok", "cron": res, "round_trip_ms": rtt_ms},
                                    200, seq_id=seq_id, rtt_ms=rtt_ms)
                return

            self._send_json({"error": "Unknown gateway endpoint"}, 404)
            return

        if path.startswith("/v1/chat/completions"):
            upstream_url = f"{UPSTREAM_BASE}/v1/chat/completions"
            forward_body = raw_body
            try:
                data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                if isinstance(data, dict):
                    if "keep_alive" not in data or data["keep_alive"] is None:
                        data["keep_alive"] = -1
                    forward_body = json.dumps(data).encode("utf-8")
            except Exception:
                forward_body = raw_body
            req = urllib.request.Request(upstream_url, data=forward_body, method="POST")
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60.0) as resp:
                    resp_data = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                    self.send_header("Content-Length", str(len(resp_data)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(resp_data)
                    return
            except urllib.error.HTTPError as he:
                err_data = he.read()
                self.send_response(he.code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_data)))
                self.end_headers()
                self.wfile.write(err_data)
                return
            except Exception as exc:
                self._send_json({"error": f"Upstream inference failure: {exc}"}, 502)
                return

        self._send_json({"error": "Not found", "path": self.path}, 404)

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_server():
    server = ThreadedHTTPServer((HOST, PORT), HermesModelHandler)
    print(f"[Hermes 8080 Model Service] Listening on http://{HOST}:{PORT}")
    print(f"[Hermes 8080 Model Service] Upstream inference engine: {UPSTREAM_BASE}")
    print(f"[Hermes 8080 Model Service] Active model: {DEFAULT_MODEL}")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[Hermes 8080 Model Service] Stopped.")


if __name__ == "__main__":
    run_server()
