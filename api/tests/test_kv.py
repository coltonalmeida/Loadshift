"""Key Value tier: it must help when up and be invisible when down.

The second half matters more than the first. Render Key Value is now where the
forecast, the weather last-known-good, the shared-key budget and the insight
cache live, and CLAUDE.md's rule is absolute: on failure serve last-known-good,
never an error page. A KV outage must degrade to the old in-process behaviour,
not to a 500.
"""
from __future__ import annotations

import json
import time

import pytest

from loadshift import cache, insights, kv, ratelimit


class FakeRedis:
    """The subset of the Valkey protocol kv.py actually uses."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.expiries: dict[str, int] = {}
        self.fail = False

    def _guard(self):
        if self.fail:
            raise ConnectionError("kv down")

    def ping(self):
        self._guard()
        return True

    def get(self, key):
        self._guard()
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self._guard()
        self.store[key] = value
        if ex:
            self.expiries[key] = ex
        return True

    def zrange(self, key, start, stop, withscores=False):
        self._guard()
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv_: kv_[1])
        got = items[start : (stop + 1 if stop >= 0 else None)]
        return got if withscores else [m for m, _ in got]

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, r: FakeRedis) -> None:
        self.r = r
        self.ops: list = []

    def zremrangebyscore(self, key, lo, hi):
        self.ops.append(("prune", key, hi))
        return self

    def zcard(self, key):
        self.ops.append(("card", key, None))
        return self

    def zadd(self, key, mapping):
        self.ops.append(("add", key, mapping))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self):
        self.r._guard()
        out = []
        for op, key, arg in self.ops:
            z = self.r.zsets.setdefault(key, {})
            if op == "prune":
                for m in [m for m, s in z.items() if s <= arg]:
                    del z[m]
                out.append(1)
            elif op == "card":
                out.append(len(z))
            elif op == "add":
                z.update(arg)
                out.append(1)
            else:
                self.r.expiries[key] = arg
                out.append(True)
        return out


@pytest.fixture
def fake_kv(monkeypatch):
    """Wire kv.py to an in-memory double and reset all module caches."""
    r = FakeRedis()
    kv.reset_for_tests()
    monkeypatch.setenv("KV_URL", "redis://fake:6379")
    monkeypatch.setattr(kv, "_connect", lambda: r)
    yield r
    kv.reset_for_tests()


@pytest.fixture
def no_kv(monkeypatch):
    """No KV_URL at all — local dev, and the shape of a total outage."""
    kv.reset_for_tests()
    monkeypatch.delenv("KV_URL", raising=False)
    yield
    kv.reset_for_tests()


# ------------------------------------------------------------------ kv basics

def test_round_trip(fake_kv):
    assert kv.set_json("k", {"a": 1}) is True
    assert kv.get_json("k") == {"a": 1}
    assert kv.available() is True
    assert kv.backend() == "render-key-value"


def test_missing_key_is_none_not_an_error(fake_kv):
    assert kv.get_json("nope") is None


def test_no_url_means_no_kv_and_no_exception(no_kv):
    assert kv.available() is False
    assert kv.get_json("k") is None
    assert kv.set_json("k", {"a": 1}) is False
    assert kv.backend() == "in-process"


def test_connection_failure_degrades_and_is_reported(monkeypatch):
    kv.reset_for_tests()
    monkeypatch.setenv("KV_URL", "redis://nope:6379")

    def boom():
        raise ConnectionError("refused")

    monkeypatch.setattr(kv, "_connect", boom)
    assert kv.available() is False
    assert "kv unreachable" in kv.backend()
    assert "refused" in (kv.last_error() or "")
    kv.reset_for_tests()


def test_mid_call_failure_does_not_propagate(fake_kv):
    kv.set_json("k", {"a": 1})
    fake_kv.fail = True
    # The client is already connected; the failure happens inside the call.
    assert kv.get_json("k") is None
    assert kv.set_json("k", {"b": 2}) is False


# ---------------------------------------------------------------- forecast cache

def _payload(generated_at="2026-08-21T12:00:00Z", stale=False):
    return {
        "generated_at": generated_at,
        "stale": stale,
        "now": {},
        "hours": [{"ts": "2026-08-21T13:00:00Z", "marginal": 400.0}],
    }


@pytest.fixture(autouse=True)
def clean_cache_state():
    cache._state.update({"payload": None, "last_error": None, "attempts": 0,
                         "fetched_at": 0.0})
    yield
    cache._state.update({"payload": None, "last_error": None, "attempts": 0,
                         "fetched_at": 0.0})


def test_fresh_instance_reads_forecast_from_kv(fake_kv):
    """The whole point: a redeployed container has empty memory and empty disk."""
    kv.set_json(kv.FORECAST_KEY, _payload())
    got = cache.get()
    assert got is not None
    assert got["generated_at"] == "2026-08-21T12:00:00Z"
    # A payload the cron wrote is current, not stale.
    assert got["stale"] is False


def test_kv_payload_beats_the_in_process_copy_after_ttl(fake_kv, monkeypatch):
    kv.set_json(kv.FORECAST_KEY, _payload("2026-08-21T12:00:00Z"))
    assert cache.get()["generated_at"] == "2026-08-21T12:00:00Z"

    # Cron writes a newer one an hour later.
    kv.set_json(kv.FORECAST_KEY, _payload("2026-08-21T13:00:00Z"))
    # Within the memory TTL the old copy is still served...
    assert cache.get()["generated_at"] == "2026-08-21T12:00:00Z"
    # ...and once it lapses the new one is picked up without a restart.
    monkeypatch.setattr(cache, "_MEM_TTL_S", 0)
    assert cache.get()["generated_at"] == "2026-08-21T13:00:00Z"


def test_kv_outage_keeps_serving_what_we_hold(fake_kv):
    kv.set_json(kv.FORECAST_KEY, _payload())
    assert cache.get() is not None
    fake_kv.fail = True
    # KV is gone. The site must not start 503-ing.
    assert cache.get() is not None


def test_falls_back_to_disk_when_kv_has_nothing(fake_kv, tmp_path, monkeypatch):
    p = tmp_path / "cache_forecast.json"
    p.write_text(json.dumps(_payload()))
    monkeypatch.setattr(cache, "CACHE_PATH", p)
    got = cache.get()
    assert got is not None
    # Disk copy is from a previous process, so it is explicitly stale.
    assert got["stale"] is True


def test_empty_everywhere_is_none_not_an_exception(no_kv, tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "absent.json")
    assert cache.get() is None


# ------------------------------------------------------------------ rate limit

def test_kv_limiter_matches_the_in_process_window(fake_kv):
    lim = ratelimit.KvLimiter(ratelimit.Limiter())
    allowed, remaining, _ = lim.check("1.2.3.4")
    assert allowed and remaining == ratelimit.PER_IP_CALLS

    for i in range(ratelimit.PER_IP_CALLS):
        assert lim.check("1.2.3.4")[0] is True
        left = lim.consume("1.2.3.4")
        assert left == ratelimit.PER_IP_CALLS - (i + 1)

    allowed, remaining, retry = lim.check("1.2.3.4")
    assert allowed is False and remaining == 0 and retry > 0
    # A different visitor is unaffected.
    assert lim.check("5.6.7.8")[0] is True


def test_budget_survives_a_restart(fake_kv):
    """The defect this fixes: a redeploy used to hand everyone a fresh allowance."""
    lim = ratelimit.KvLimiter(ratelimit.Limiter())
    for _ in range(ratelimit.PER_IP_CALLS):
        lim.consume("9.9.9.9")
    assert lim.check("9.9.9.9")[0] is False

    # New process, new in-process state, same Key Value.
    restarted = ratelimit.KvLimiter(ratelimit.Limiter())
    assert restarted.check("9.9.9.9")[0] is False
    assert restarted.remaining("9.9.9.9") == 0


def test_limiter_falls_back_to_memory_when_kv_is_down(fake_kv):
    lim = ratelimit.KvLimiter(ratelimit.Limiter())
    lim.consume("1.1.1.1")
    fake_kv.fail = True
    # Must answer from the local limiter rather than raising.
    allowed, remaining, _ = lim.check("1.1.1.1")
    assert allowed is True
    assert remaining == ratelimit.PER_IP_CALLS


def test_global_daily_cap_is_shared(fake_kv):
    lim = ratelimit.KvLimiter(ratelimit.Limiter(per_client=100, daily=3))
    for i in range(3):
        assert lim.check(f"ip{i}")[0] is True
        lim.consume(f"ip{i}")
    # Fourth distinct visitor is refused by the global budget, not their own.
    assert lim.check("ip-new")[0] is False


# --------------------------------------------------------------- insight cache

def test_insight_cache_survives_a_process_restart(fake_kv):
    insights._cache.clear()
    key = "digest-abc"
    insights._store(key, {"summary": "s", "recommendations": [], "model": "m"})
    assert insights._cached(key)["summary"] == "s"

    # Simulate a redeploy: in-process LRU gone, Key Value intact.
    insights._cache.clear()
    hit = insights._cached(key)
    assert hit is not None and hit["summary"] == "s"


def test_insight_cache_miss_is_none(fake_kv):
    insights._cache.clear()
    assert insights._cached("never-stored") is None


def test_insight_cache_works_without_kv(no_kv):
    insights._cache.clear()
    insights._store("k", "answer")
    assert insights._cached("k") == "answer"
