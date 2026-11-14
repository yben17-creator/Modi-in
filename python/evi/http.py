"""Rate-limited, cached HTTP client shared by all providers."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import requests

from .store import Store


class HttpError(Exception):
    def __init__(self, status: int, url: str, msg: str = ""):
        super().__init__(f"HTTP {status} for {url} {msg}".strip())
        self.status = status
        self.url = url


class RateLimiter:
    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second if per_second > 0 else 0
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


class CachedHttp:
    """GET with SQLite cache. `secret_params` are excluded from the cache key (API keys)."""

    def __init__(self, store: Store, name: str, per_second: float, headers: dict[str, str] | None = None,
                 retries: int = 3, timeout: float = 30.0):
        self.store = store
        self.name = name
        self.limiter = RateLimiter(per_second)
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        self.retries = retries
        self.timeout = timeout

    def _key(self, url: str, params: dict | None, secret: tuple[str, ...]) -> str:
        p = {k: v for k, v in (params or {}).items() if k not in secret}
        return f"{self.name}|{url}?{urlencode(sorted(p.items()))}"

    def fetched_at(self, url: str, params: dict | None = None, secret: tuple[str, ...] = ()) -> str | None:
        ts = self.store.cache_fetched_at(self._key(url, params, secret))
        return datetime.fromtimestamp(ts).replace(microsecond=0).isoformat() if ts else None

    def get_bytes(self, url: str, params: dict | None = None, ttl_h: float = 12, secret: tuple[str, ...] = (),
                  allow_404: bool = True) -> bytes | None:
        key = self._key(url, params, secret)
        hit = self.store.cache_get(key, ttl_h * 3600)
        if hit is not None:
            status, body = hit
            return None if status == 404 else body
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            self.limiter.wait()
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 200:
                self.store.cache_put(key, 200, r.content)
                return r.content
            if r.status_code == 404 and allow_404:
                self.store.cache_put(key, 404, b"")
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                last_exc = HttpError(r.status_code, url)
                continue
            raise HttpError(r.status_code, url, r.text[:200])
        # network failed: fall back to stale cache if any
        stale = self.store.cache_get(key, -1)
        if stale is not None and stale[0] == 200:
            return stale[1]
        raise last_exc or HttpError(0, url, "unknown error")

    def get_json(self, url: str, params: dict | None = None, ttl_h: float = 12, secret: tuple[str, ...] = ()) -> Any:
        b = self.get_bytes(url, params, ttl_h, secret)
        return None if b is None else json.loads(b)
