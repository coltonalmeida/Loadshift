"""Shared-key budget for the AI insight endpoints.

The shared Gemini key is a free tier funded by one person, so anonymous
visitors get a small stated allowance and are told to bring their own key for
more. Callers supplying their own key never reach this module.

check() and consume() are deliberately separate: a cached answer should report
the remaining allowance without spending any of it.

Counters live in Render Key Value when it is reachable. In process memory they
reset on every deploy — handing every visitor a fresh allowance several times
an hour — and the global daily cap multiplies by the instance count, which
defeats the point of a budget on a key one person pays for. The in-process
Limiter below stays as the fallback for local dev and a KV outage.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

from . import kv

PER_IP_CALLS = 6
PER_IP_WINDOW_S = 600
DAILY_CALLS = 300
DAY_S = 86_400

# Bounded so a scraper rotating addresses cannot grow this without limit; the
# eviction victim is the least recently seen client, whose window has almost
# certainly lapsed anyway.
MAX_CLIENTS = 4096


class Limiter:
    def __init__(
        self,
        per_client: int = PER_IP_CALLS,
        window_s: int = PER_IP_WINDOW_S,
        daily: int = DAILY_CALLS,
    ) -> None:
        self.per_client = per_client
        self.window_s = window_s
        self.daily = daily
        self._clients: OrderedDict[str, deque[float]] = OrderedDict()
        self._day: deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float, client: str) -> deque[float]:
        hits = self._clients.get(client)
        if hits is None:
            hits = deque()
            self._clients[client] = hits
        self._clients.move_to_end(client)
        while hits and now - hits[0] > self.window_s:
            hits.popleft()
        while self._day and now - self._day[0] > DAY_S:
            self._day.popleft()
        while len(self._clients) > MAX_CLIENTS:
            self._clients.popitem(last=False)
        return hits

    def check(self, client: str) -> tuple[bool, int, int]:
        """(allowed, remaining_for_this_client, retry_after_s)."""
        now = time.time()
        with self._lock:
            hits = self._prune(now, client)
            remaining = max(0, self.per_client - len(hits))
            if len(self._day) >= self.daily:
                return False, 0, int(DAY_S - (now - self._day[0])) + 1
            if not remaining:
                return False, 0, int(self.window_s - (now - hits[0])) + 1
            return True, remaining, 0

    def consume(self, client: str) -> int:
        """Record one call. Returns the remaining allowance after it."""
        now = time.time()
        with self._lock:
            hits = self._prune(now, client)
            hits.append(now)
            self._day.append(now)
            return max(0, self.per_client - len(hits))

    def remaining(self, client: str) -> int:
        now = time.time()
        with self._lock:
            hits = self._prune(now, client)
            if len(self._day) >= self.daily:
                return 0
            return max(0, self.per_client - len(hits))


class KvLimiter:
    """Same contract as Limiter, backed by Valkey sorted sets.

    ZREMRANGEBYSCORE + ZCARD is the deque prune-and-count, and per-key EXPIRE
    replaces the MAX_CLIENTS LRU: an address that stops calling evicts itself.
    Any KV failure returns None from the kv helpers, and every method below
    then defers to `local` so a cache outage never becomes a 500.
    """

    def __init__(self, local: Limiter) -> None:
        self.local = local
        self.per_client = local.per_client
        self.window_s = local.window_s
        self.daily = local.daily

    def _day_count(self, now: float) -> int | None:
        return kv.window_count(kv.DAY_KEY, DAY_S, now)

    def check(self, client: str) -> tuple[bool, int, int]:
        now = time.time()
        day = self._day_count(now)
        used = kv.window_count(kv.client_key(client), self.window_s, now)
        if day is None or used is None:
            return self.local.check(client)

        if day >= self.daily:
            oldest = kv.window_oldest(kv.DAY_KEY, DAY_S, now)
            retry = int(DAY_S - (now - oldest)) + 1 if oldest else DAY_S
            return False, 0, retry
        remaining = max(0, self.per_client - used)
        if not remaining:
            oldest = kv.window_oldest(kv.client_key(client), self.window_s, now)
            retry = int(self.window_s - (now - oldest)) + 1 if oldest else self.window_s
            return False, 0, retry
        return True, remaining, 0

    def consume(self, client: str) -> int:
        now = time.time()
        used = kv.window_add(kv.client_key(client), self.window_s, now)
        if used is None:
            return self.local.consume(client)
        kv.window_add(kv.DAY_KEY, DAY_S, now)
        return max(0, self.per_client - used)

    def remaining(self, client: str) -> int:
        now = time.time()
        day = self._day_count(now)
        used = kv.window_count(kv.client_key(client), self.window_s, now)
        if day is None or used is None:
            return self.local.remaining(client)
        if day >= self.daily:
            return 0
        return max(0, self.per_client - used)


shared = KvLimiter(Limiter())
