import time


class SlidingWindowRateLimiter:
    """In-memory per-key sliding-window limiter.

    State is per-process: under multiple gunicorn workers the effective limit is
    multiplied by the worker count. A shared store (e.g. Redis) would be needed
    for a global limit; that is out of scope for this project.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        fresh = [t for t in self._hits.get(key, ()) if t > cutoff]
        fresh.append(now)
        self._hits[key] = fresh
        return len(fresh) <= self._limit
