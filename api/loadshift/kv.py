"""Render Key Value (Valkey) client — the only thing that survives a deploy.

Render containers have an ephemeral filesystem: `api/data/` is wiped on every
deploy, which is why the forecast cache, the weather last-known-good, the
shared-key budget and the insight cache all used to reset to nothing several
times an hour. They live here instead.

Every helper degrades to None rather than raising. `KV_URL` is unset in local
dev and may be briefly unreachable in production; in both cases callers fall
through to the in-process/disk path they used before. Key Value must never
become a new way for the site to fail — see the last-known-good rule in
CLAUDE.md.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

# Short: a request path may touch this, and a hung socket is worse than a miss.
CONNECT_TIMEOUT_S = 2
SOCKET_TIMEOUT_S = 2

PREFIX = "loadshift"
FORECAST_KEY = f"{PREFIX}:forecast:v1"
FORECAST_META_KEY = f"{PREFIX}:forecast:meta"
WEATHER_KEY = f"{PREFIX}:weather:last_good"


def insight_key(digest: str) -> str:
    return f"{PREFIX}:insight:{digest}"


def client_key(client: str) -> str:
    return f"{PREFIX}:rl:c:{client}"


DAY_KEY = f"{PREFIX}:rl:day"

_lock = threading.Lock()
_client = None
_resolved = False
_last_error: str | None = None
# A dead Valkey must not cost every request a 2s connect. After a failure we
# stop trying for this long, then allow one probe through.
_RETRY_AFTER_S = 30
_next_probe = 0.0


def url() -> str | None:
    return os.environ.get("KV_URL") or None


def _connect():
    """Build a client and prove it answers, or return None."""
    target = url()
    if not target:
        return None
    import redis  # imported lazily so local dev without the package still runs

    c = redis.Redis.from_url(
        target,
        socket_timeout=SOCKET_TIMEOUT_S,
        socket_connect_timeout=CONNECT_TIMEOUT_S,
        decode_responses=True,
        health_check_interval=30,
    )
    c.ping()
    return c


def get_client():
    """Live client, or None. Never raises."""
    global _client, _resolved, _last_error, _next_probe
    with _lock:
        if _client is not None:
            return _client
        if _resolved and time.time() < _next_probe:
            return None
        _resolved = True
        try:
            _client = _connect()
            if _client is not None:
                _last_error = None
                print(f"[kv] connected ({url().rsplit('@', 1)[-1]})")
        except Exception as e:  # noqa: BLE001 - any failure degrades to no KV
            _last_error = f"{type(e).__name__}: {e}"[:200]
            _client = None
            _next_probe = time.time() + _RETRY_AFTER_S
            print(f"[kv] unavailable, falling back to local cache: {_last_error}")
        return _client


def available() -> bool:
    return get_client() is not None


def backend() -> str:
    """What the cache is actually being served from, for /api/health."""
    if not url():
        return "in-process"
    return "render-key-value" if available() else "in-process (kv unreachable)"


def last_error() -> str | None:
    return _last_error


def _drop() -> None:
    """Forget a client that just failed mid-call so the next get_client retries."""
    global _client, _next_probe
    with _lock:
        _client = None
        _next_probe = time.time() + _RETRY_AFTER_S


def get_json(key: str):
    c = get_client()
    if c is None:
        return None
    try:
        raw = c.get(key)
    except Exception as e:  # noqa: BLE001
        _note(f"get {key}", e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def set_json(key: str, value, ttl_s: int | None = None) -> bool:
    c = get_client()
    if c is None:
        return False
    try:
        c.set(key, json.dumps(value, default=str), ex=ttl_s)
        return True
    except Exception as e:  # noqa: BLE001
        _note(f"set {key}", e)
        return False


def _note(what: str, e: Exception) -> None:
    global _last_error
    _last_error = f"{type(e).__name__}: {e}"[:200]
    print(f"[kv] {what} failed: {_last_error}")
    _drop()


def window_count(key: str, window_s: int, now: float) -> int | None:
    """Calls in the trailing window. None means KV is unavailable."""
    c = get_client()
    if c is None:
        return None
    try:
        pipe = c.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_s)
        pipe.zcard(key)
        return int(pipe.execute()[1])
    except Exception as e:  # noqa: BLE001
        _note(f"count {key}", e)
        return None


def window_add(key: str, window_s: int, now: float) -> int | None:
    """Record one call and return the new count. None means KV is unavailable."""
    c = get_client()
    if c is None:
        return None
    try:
        pipe = c.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_s)
        # The member must be unique per call or ZADD silently overwrites and the
        # call goes uncounted. A timestamp is not unique enough: time.time() is
        # ~16ms-granular on Windows and two concurrent requests can share a
        # microsecond anywhere. The score stays `now` — that is what we prune on.
        pipe.zadd(key, {uuid.uuid4().hex: now})
        pipe.zcard(key)
        # Bounded lifetime: an IP that never returns evicts itself. This is what
        # replaces the old MAX_CLIENTS LRU, and it is strictly more correct.
        pipe.expire(key, window_s + 60)
        return int(pipe.execute()[2])
    except Exception as e:  # noqa: BLE001
        _note(f"add {key}", e)
        return None


def window_oldest(key: str, window_s: int, now: float) -> float | None:
    """Score of the oldest call still in the window, for Retry-After."""
    c = get_client()
    if c is None:
        return None
    try:
        got = c.zrange(key, 0, 0, withscores=True)
        return float(got[0][1]) if got else None
    except Exception as e:  # noqa: BLE001
        _note(f"oldest {key}", e)
        return None


def reset_for_tests() -> None:
    """Drop cached connection state so a test can point KV_URL somewhere else."""
    global _client, _resolved, _last_error, _next_probe
    with _lock:
        _client = None
        _resolved = False
        _last_error = None
        _next_probe = 0.0
