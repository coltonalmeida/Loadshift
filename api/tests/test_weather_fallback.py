"""Weather fallback: a rate-limited upstream must degrade, never 503.

The failure this guards against is specific: Render wipes api/data/ on every
deploy, so an instance can boot straight into an Open-Meteo 429 with no
last-good on disk. Without the committed seed the whole forecast disappears.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from loadshift import weather


FUTURE = pd.date_range("2026-08-22 01:00", periods=24, freq="h")


def _snapshot(hours: int = 72, start: str = "2026-08-21 00:00") -> dict:
    idx = pd.date_range(start, periods=hours, freq="h")
    return {
        "hourly": {
            "time": [t.strftime("%Y-%m-%dT%H:%M") for t in idx],
            "temperature_2m": [20 + (t.hour - 12) * 0.5 for t in idx],
            "wind_speed_100m": [10.0] * hours,
            "cloud_cover": [50.0] * hours,
            "shortwave_radiation": [max(0.0, 400 - abs(t.hour - 13) * 60) for t in idx],
        }
    }


def test_seed_artifact_is_present_and_loadable():
    """Ships in the repo, so it must survive a fresh checkout."""
    assert weather.SEED.exists(), "committed weather seed is missing"
    got = weather._load_stored(weather.SEED)
    assert got is not None
    df, _age = got
    assert list(df.columns) == weather.WEATHER_COLS
    assert len(df) >= 24


def test_by_hour_of_day_fills_a_future_index_without_nan():
    df = weather._to_frame(_snapshot()["hourly"])
    out = weather.by_hour_of_day(df, FUTURE)
    assert list(out.index) == list(FUTURE)
    assert not out[weather.WEATHER_COLS].isna().any().any()
    # Diurnal shape preserved: solar peaks near midday, not flat.
    assert out["shortwave_radiation"].max() > out["shortwave_radiation"].min()


def test_falls_back_to_seed_when_live_fails_and_no_last_good(monkeypatch, tmp_path):
    """The cold-boot case: 429 on a fresh instance with an empty api/data/."""
    def boom(days, attempts):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(weather, "_fetch_live", boom)
    monkeypatch.setattr(weather, "LAST_GOOD", tmp_path / "absent.json")

    df = weather.forecast()
    assert df.attrs["source"] == "seed"
    assert len(df) > 0


def test_last_good_wins_over_seed_and_expires(monkeypatch, tmp_path):
    def boom(days, attempts):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(weather, "_fetch_live", boom)
    path = tmp_path / "last.json"
    monkeypatch.setattr(weather, "LAST_GOOD", path)

    fresh = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(hours=2)
    path.write_text(json.dumps({"fetched_at": fresh.isoformat(), "payload": _snapshot()}))
    assert weather.forecast().attrs["source"] == "last_good"

    stale = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(
        hours=weather.FALLBACK_MAX_AGE_H + 5
    )
    path.write_text(json.dumps({"fetched_at": stale.isoformat(), "payload": _snapshot()}))
    assert weather.forecast().attrs["source"] == "seed"


def test_live_success_stores_last_good_and_marks_source(monkeypatch, tmp_path):
    path = tmp_path / "last.json"
    monkeypatch.setattr(weather, "LAST_GOOD", path)
    monkeypatch.setattr(weather, "DATA_DIR", tmp_path)
    monkeypatch.setattr(weather, "_fetch_live", lambda days, attempts: _snapshot())

    df = weather.forecast()
    assert df.attrs["source"] == "live"
    assert path.exists(), "a good live response must be persisted for next time"


def test_fetch_live_retries_before_giving_up(monkeypatch):
    calls = {"n": 0}

    class Resp:
        def raise_for_status(self):
            calls["n"] += 1
            raise RuntimeError("429")

    monkeypatch.setattr(weather.time, "sleep", lambda s: None)
    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: Resp())
    with pytest.raises(RuntimeError):
        weather._fetch_live(days=3, attempts=3)
    assert calls["n"] == 3


def test_aligned_reports_source_and_covers_index(monkeypatch, tmp_path):
    monkeypatch.setattr(weather, "LAST_GOOD", tmp_path / "absent.json")
    monkeypatch.setattr(weather, "_fetch_live", lambda days, attempts: (_ for _ in ()).throw(RuntimeError("429")))

    out = weather.aligned(FUTURE)
    assert out.attrs["source"] == "seed"
    assert list(out.index) == list(FUTURE)
    assert not out[weather.WEATHER_COLS].isna().any().any()


def test_raises_only_when_nothing_at_all_is_available(monkeypatch, tmp_path):
    monkeypatch.setattr(weather, "LAST_GOOD", tmp_path / "absent.json")
    monkeypatch.setattr(weather, "SEED", tmp_path / "also_absent.json")
    monkeypatch.setattr(weather, "_fetch_live", lambda days, attempts: (_ for _ in ()).throw(RuntimeError("429")))
    with pytest.raises(RuntimeError, match="weather unavailable"):
        weather.forecast()
