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

        self._send_json({"error": "Not found", "path": self.path}, 404)

    def do_POST(self):
        path, _, _ = self.path.partition("?")
        if path.startswith("/v1/chat/completions"):
            content_len = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"

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
