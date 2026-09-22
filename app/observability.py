from __future__ import annotations

import time

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "trace_ai_http_requests_total",
    "HTTP requests processed by TRACE-AI",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "trace_ai_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"


async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = _route_label(request)
        HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
        HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - started)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
