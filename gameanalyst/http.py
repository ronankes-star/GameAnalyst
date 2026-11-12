"""A polite JSON client: one request at a time, a minimum gap between two requests to the same host, retries with
backoff. A host that answers 429 ("too many requests") gets a longer gap, up to `max_interval`. The gap shrinks
slowly again while the host answers normally."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

USER_AGENT = "GameAnalyst/0.1 (public-data research)"
RETRY_STATUSES = {429, 500, 502, 503, 504}

# transport(url, headers, timeout) -> (status, response headers, body)
Transport = Callable[[str, dict, float], tuple[int, dict, bytes]]


class HttpError(Exception):
    def __init__(self, url: str, status: int | None, detail: str = ""):
        super().__init__(f"HTTP {status} for {url} {detail}".strip())
        self.url = url
        self.status = status


def urllib_transport(url: str, headers: dict, timeout: float) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


@dataclass
class Http:
    transport: Transport = urllib_transport
    min_interval: float = 0.3  # seconds between two requests to the same host
    max_interval: float = 5.0  # the longest gap after many 429 answers
    max_retries: int = 5
    timeout: float = 30.0
    backoff_base: float = 1.0
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    requests_made: int = field(default=0, init=False)
    _last: dict[str, float] = field(default_factory=dict, init=False, repr=False)  # host -> time of last request
    _gap: dict[str, float] = field(default_factory=dict, init=False, repr=False)  # host -> its gap right now

    def get_json(self, url: str, params: dict | None = None) -> dict:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, safe=',')}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        host = urllib.parse.urlsplit(url).netloc
        status: int | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            try:
                status, response_headers, body = self.transport(url, headers, self.timeout)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                status, response_headers, body = None, {}, str(e).encode()
            self.requests_made += 1
            self._adapt(host, status)
            if status == 200:
                return json.loads(body)
            if status is not None and status not in RETRY_STATUSES:
                raise HttpError(url, status, body[:200].decode("utf-8", "replace"))
            if attempt < self.max_retries:
                self.sleep(self._wait_before_retry(attempt, response_headers))
        raise HttpError(url, status, "(gave up after retries)")

    def gap(self, host: str) -> float:
        return self._gap.get(host, self.min_interval)

    def _throttle(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            wait = self.gap(host) - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def _adapt(self, host: str, status: int | None) -> None:
        """Double the host's gap after a 429. After a normal answer, shrink it by 2% (about 35 answers to halve)."""
        if status == 429:
            self._gap[host] = min(self.gap(host) * 2, self.max_interval)
        elif status == 200 and host in self._gap:
            self._gap[host] = max(self.gap(host) * 0.98, self.min_interval)

    def _wait_before_retry(self, attempt: int, headers: dict) -> float:
        retry_after = {k.lower(): v for k, v in headers.items()}.get("retry-after")
        if retry_after is not None:
            try:
                return min(float(retry_after), 120.0)
            except ValueError:
                pass
        return self.backoff_base * 2**attempt + random.uniform(0, 0.5)
