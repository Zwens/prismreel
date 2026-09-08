"""In-process sliding-window rate limiter for AI-cost-triggering endpoints.

This is deliberately not a general-purpose limiter: PrismReel calls out to
paid vendor APIs (DashScope, Kling, Vidu, Ark) per generation request, so an
unauthenticated or compromised caller hammering /generate_* burns real money
per request, not just server CPU. A dependency-free in-memory limiter is
enough for the "VPS shared by a small team" deployment this guards — it
resets on restart and doesn't coordinate across multiple backend processes,
which is fine at that scale and avoids pulling in Redis for it.
"""

import time
import threading
from collections import deque

_lock = threading.Lock()
_hits: dict[str, deque] = {}


def is_rate_limited(key: str, max_calls: int, window_seconds: float) -> bool:
    """Return True if *key* has already made >= max_calls within window_seconds."""
    now = time.monotonic()
    with _lock:
        bucket = _hits.setdefault(key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= max_calls:
            return True
        bucket.append(now)
        return False
