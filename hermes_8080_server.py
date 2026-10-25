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

HOST = os.environ.get("HERMES_8080_HOST", "127.0.0.1")
PORT = int(os.environ.get("HERMES_8080_PORT", "8080"))
UPSTREAM_BASE = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("HERMES_DEFAULT_MODEL", "qwen3:4b")


class HermesModelHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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

            if path == "/gateway/v1/rpc":
                req_id = body_json.get("id")
                method = body_json.get("method", "")
                params = body_json.get("params", {})
                rpc_res = execute_gateway_rpc(method, params)
                out = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": rpc_res.get("result"),
                    "error": rpc_res.get("error"),
                    "status": "error" if rpc_res.get("error") else "ok"
                }
                status_code = 400 if rpc_res.get("error") else 200
                self._send_json(out, status_code)
                return

            elif path == "/gateway/v1/tasks":
                cmd = body_json.get("command") or body_json.get("cmd", "ping")
                params = body_json.get("params", body_json)
                res = execute_task_command(cmd, params)
                self._send_json({"status": "ok", "task": res})
                return

            elif path == "/gateway/v1/crons":
                action = body_json.get("action", "update")
                cron_id = body_json.get("id") or body_json.get("cron_id")
                if action == "trigger":
                    res = trigger_cron_job(cron_id)
                    self._send_json({"status": "ok", "triggered": res})
                else:
                    res = update_cron_job(cron_id, body_json)
                    self._send_json({"status": "ok", "cron": res})
                return

            self._send_json({"error": "Unknown gateway endpoint"}, 404)
            return

        if path.startswith("/v1/chat/completions"):
            upstream_url = f"{UPSTREAM_BASE}/v1/chat/completions"
            req = urllib.request.Request(upstream_url, data=raw_body, method="POST")
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
