"""
tests/test_deep_dispatch_module.py
Comprehensive test suite for the Deep Route Dispatch Module:
1. HTTPRequest and HTTPResponse data contracts and streaming support.
2. Transparent tuple unpacking for backward compatibility: payload, status, headers = router.dispatch(...)
3. Automatic CORS and OPTIONS preflight negotiation.
4. Server-Sent Events (SSE) stream dispatch in-memory without sockets.
5. Domain route mounting and prefix routing.
6. Error handling, Pydantic schema enforcement, and Encore tracing header propagation.
"""

import unittest
from typing import Dict, Any, Iterator
from pydantic import BaseModel

from hud.type_safe_router import (
    EncoreObservabilityEngine, TypeSafeRouter,
    HTTPRequest, HTTPResponse
)


class SampleItem(BaseModel):
    name: str
    count: int


class SampleItemResponse(BaseModel):
    item_id: str
    name: str
    total: int


class DeepDispatchModuleTests(unittest.TestCase):
    def setUp(self):
        self.observability = EncoreObservabilityEngine(service_name="test-deep-dispatch", max_traces=50)
        self.router = TypeSafeRouter(observability=self.observability)

    def test_http_request_and_response_contracts(self):
        req = HTTPRequest(path="/test", method="GET", headers={"User-Agent": "UnitTests"})
        self.assertEqual(req.path, "/test")
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.headers.get("User-Agent"), "UnitTests")

        resp = HTTPResponse(status_code=200, payload={"ok": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.payload, {"ok": True})
        self.assertEqual(resp.headers.get("Content-Type"), "application/json; charset=utf-8")
        self.assertFalse(resp.is_stream)

        # Transparent tuple unpacking
        payload, status, headers = resp
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(headers.get("Content-Type"), "application/json; charset=utf-8")

    def test_legacy_dispatch_and_tuple_unpacking(self):
        def ping_handler(**kwargs):
            return {"pong": True}

        self.router.register("/api/ping", "GET", ping_handler)

        # 1. Calling with positional args returns unpackable HTTPResponse
        payload, status, headers = self.router.dispatch("/api/ping", "GET", headers={})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"pong": True})
        self.assertIn("X-Encore-Trace-ID", headers)

        # 2. Calling with HTTPRequest object returns HTTPResponse directly
        req = HTTPRequest(path="/api/ping", method="GET")
        resp = self.router.dispatch(req)
        self.assertIsInstance(resp, HTTPResponse)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"pong": True})

    def test_cors_options_preflight(self):
        def dummy_handler(**kwargs):
            return {"status": "ok"}

        self.router.register("/api/data", "POST", dummy_handler)

        # Preflight OPTIONS request
        req = HTTPRequest(path="/api/data", method="OPTIONS")
        resp = self.router.dispatch(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
        self.assertIn("OPTIONS", resp.headers.get("Access-Control-Allow-Methods", ""))

    def test_streaming_sse_generator(self):
        def sample_sse_stream(**kwargs):
            def event_generator() -> Iterator[bytes]:
                yield b"event: ping\ndata: 1\n\n"
                yield b"event: telemetry\ndata: 2\n\n"
            return HTTPResponse(
                status_code=200,
                headers={"Content-Type": "text/event-stream; charset=utf-8"},
                body=event_generator()
            )

        self.router.register("/api/stream", "GET", sample_sse_stream)

        req = HTTPRequest(path="/api/stream", method="GET")
        resp = self.router.dispatch(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.is_stream)
        self.assertEqual(resp.headers.get("Content-Type"), "text/event-stream; charset=utf-8")

        # In-memory evaluation of stream chunks without network sockets
        chunks = list(resp.body)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], b"event: ping\ndata: 1\n\n")
        self.assertEqual(chunks[1], b"event: telemetry\ndata: 2\n\n")

    def test_pydantic_schema_validation_in_deep_module(self):
        def create_item(request_data: SampleItem, **kwargs):
            return SampleItemResponse(
                item_id="item-123",
                name=request_data.name,
                total=request_data.count * 10
            )

        self.router.register(
            "/api/items", "POST",
            create_item,
            request_model=SampleItem,
            response_model=SampleItemResponse
        )

        # Valid payload
        resp = self.router.dispatch(HTTPRequest(
            path="/api/items",
            method="POST",
            body={"name": "Widget", "count": 5}
        ))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["item_id"], "item-123")
        self.assertEqual(resp.json()["total"], 50)

        # Invalid payload (missing count)
        bad_resp = self.router.dispatch(HTTPRequest(
            path="/api/items",
            method="POST",
            body={"name": "Widget"}
        ))
        self.assertEqual(bad_resp.status_code, 400)
        self.assertEqual(bad_resp.json()["status"], "validation_error")

    def test_prefix_route_matching(self):
        def file_handler(path: str, **kwargs):
            subpath = path[len("/files/"):]
            return {"file": subpath}

        self.router.register("/files/*", "GET", file_handler)

        resp = self.router.dispatch(HTTPRequest(path="/files/documents/report.pdf", method="GET"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"file": "documents/report.pdf"})


if __name__ == "__main__":
    unittest.main()
