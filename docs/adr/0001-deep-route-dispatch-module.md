---
status: accepted
date: 2026-10-26
---

# Deep Route Dispatch Module and Standard Library Transport

We consolidate all HTTP route handling, static asset delivery, and Server-Sent Events streaming behind a single in-process dispatch seam (`dispatch(request) -> HTTPResponse`) in `hud/type_safe_router.py`, reducing `hud_server.py` to a thin network socket adapter.

## Context and Decision
`hud_server.py` had grown into an 1,846-line monolith with a 600-line route matching ladder that bypassed `TypeSafeRouter`, inspected private router state, and embedded business logic directly within `do_GET` and `do_POST`. We evaluated migrating to an external framework (such as FastAPI or Starlette), but rejected external dependencies to preserve zero-dependency deployment and runtime autonomy across Hostinger VPS environments.

## Consequences
- Route handlers and schemas are partitioned into cohesive domain route modules under `hud/routes/`.
- Cross-cutting concerns (CSP security headers, CORS negotiation, W3C/Encore tracing, and gateway HMAC authentication) execute within an internal middleware pipeline.
- Streaming responses (SSE) yield chunks across the exact same seam via `Iterator[bytes]`, making all endpoints testable in-memory without binding OS network sockets.
