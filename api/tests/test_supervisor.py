"""The refresh supervisor: step in only when nothing else is refreshing.

This exists because of a real outage. The web service was deployed with the
in-process scheduler removed but before the cron job existed, so the one-shot
warm-up refreshed once, exited, and left the forecast frozen and silently
ageing. The supervisor's job is to make that state impossible without
reintroducing a second rebuilder that races the cron.
"""
from __future__ import annotations

import pandas as pd
import pytest

from loadshift import cache, kv, main


@pytest.fixture
def refreshes(monkeypatch):
    """Record calls to cache.refresh() instead of rebuilding for real."""
    calls = []

    def fake_refresh():
        calls.append(1)
        return True

    monkeypatch.setattr(cache, "refresh", fake_refresh)
    return calls


def _iso(seconds_ago: float) -> str:
    ts = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(seconds=seconds_ago)
    return ts.isoformat() + "Z"


def _payload(age_s: float) -> dict:
    return {"generated_at": _iso(age_s), "stale": False, "now": {}, "hours": []}


@pytest.fixture
def state(monkeypatch):
    """Control what the cache and Key Value appear to hold."""

    class S:
        payload: dict | None = None
        meta: dict | None = None

    s = S()
    monkeypatch.setattr(cache, "get", lambda: s.payload)
    monkeypatch.setattr(
        kv, "get_json", lambda key: s.meta if key == kv.FORECAST_META_KEY else None
    )
    return s


# ----------------------------------------------------- cron healthy: stand down

def test_healthy_cron_means_the_web_service_does_nothing(state, refreshes):
    state.meta = {"ran_at": _iso(300), "ok": True}
    state.payload = _payload(300)
    main._supervise_once()
    assert refreshes == []
    assert main.refresher() == "cron"


def test_a_failing_but_live_cron_still_owns_the_retry(state, refreshes):
    """It reported in, so it will run again. Racing it does not help."""
    state.meta = {"ran_at": _iso(300), "ok": False, "error": "IESO timeout"}
    state.payload = _payload(9999)
    main._supervise_once()
    assert refreshes == []


def test_stale_payload_is_left_alone_while_the_cron_is_healthy(state, refreshes):
    state.meta = {"ran_at": _iso(60), "ok": True}
    state.payload = None
    main._supervise_once()
    assert refreshes == []


# ------------------------------------------------------- no cron: step in

def test_no_cron_history_at_all_triggers_a_rebuild(state, refreshes):
    """Exactly the live state that froze: new code, Blueprint not yet created."""
    state.meta = None
    state.payload = _payload(4000)
    main._supervise_once()
    assert refreshes == [1]
    assert main.refresher() == "web-fallback"


def test_a_cron_that_stopped_reporting_triggers_a_rebuild(state, refreshes):
    state.meta = {"ran_at": _iso(main.CRON_GRACE_S + 600), "ok": True}
    state.payload = _payload(4000)
    main._supervise_once()
    assert refreshes == [1]


def test_empty_cache_and_no_cron_triggers_a_rebuild(state, refreshes):
    state.meta = None
    state.payload = None
    main._supervise_once()
    assert refreshes == [1]


def test_a_fresh_payload_is_not_rebuilt_even_without_a_cron(state, refreshes):
    """The supervisor is a safety net, not a second scheduler."""
    state.meta = None
    state.payload = _payload(120)
    main._supervise_once()
    assert refreshes == []


def test_rebuild_happens_once_the_payload_passes_the_age_limit(state, refreshes):
    state.meta = None
    state.payload = _payload(main.MAX_PAYLOAD_AGE_S + 60)
    main._supervise_once()
    assert refreshes == [1]


# ------------------------------------------------------------------ robustness

def test_unparseable_cron_timestamp_counts_as_no_cron(state, refreshes):
    state.meta = {"ran_at": "not a timestamp"}
    state.payload = _payload(4000)
    main._supervise_once()
    assert refreshes == [1]


def test_a_cron_timestamp_from_the_future_is_not_trusted(state):
    state.meta = {"ran_at": _iso(-3600)}
    assert main.cron_is_healthy() is False


def test_unparseable_payload_timestamp_triggers_a_rebuild(state, refreshes):
    state.meta = None
    state.payload = {"generated_at": "garbage", "hours": []}
    main._supervise_once()
    assert refreshes == [1]


class _StopLoop(Exception):
    """Sentinel to break the supervisor's infinite loop from inside sleep()."""


def test_a_failing_refresh_does_not_kill_the_supervisor(state, monkeypatch):
    """The thread must outlive any single failure, or the site freezes again."""
    state.meta = None
    state.payload = None
    attempts = []

    def boom():
        attempts.append(1)
        raise RuntimeError("IESO unreachable")

    monkeypatch.setattr(cache, "refresh", boom)

    # Let the loop run three ticks, then break out of it.
    def fake_sleep(_seconds):
        if len(attempts) >= 3:
            raise _StopLoop
    monkeypatch.setattr(main.time, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        main._supervisor()

    # It kept trying rather than dying on the first exception.
    assert len(attempts) == 3


def test_the_supervisor_ticks_faster_while_there_is_nothing_to_serve(state, monkeypatch):
    state.meta = {"ran_at": _iso(60), "ok": True}  # healthy cron, so no rebuilds
    slept = []

    def fake_sleep(seconds):
        slept.append(seconds)
        if len(slept) >= 2:
            raise _StopLoop
    monkeypatch.setattr(main.time, "sleep", fake_sleep)

    state.payload = None
    with pytest.raises(_StopLoop):
        main._supervisor()
    assert slept[0] == main.TICK_EMPTY_S

    slept.clear()
    state.payload = _payload(60)
    with pytest.raises(_StopLoop):
        main._supervisor()
    assert slept[0] == main.TICK_IDLE_S
