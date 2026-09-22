"""Small fail-closed per-process limiter; use a gateway/WAF for distributed limits."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_requests: dict[str, deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(request: Request, limit: int, window_seconds: int = 60) -> None:
    now = time.monotonic()
    key = f"{request.method}:{request.url.path}:{client_key(request)}"
    bucket = _requests[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": str(window_seconds)})
    bucket.append(now)
