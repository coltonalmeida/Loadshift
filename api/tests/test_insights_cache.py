"""Prompt canonicalisation and the cron's sample-report warm-up.

The load-bearing property here is that statistics reaching us from the browser
and the same statistics computed server-side by the cron produce the SAME cache
digest. If they don't, the pre-warm generates a report nobody ever reads and the
first visitor still pays the latency and the quota.
"""
from __future__ import annotations

import json

import pytest

from loadshift import insights, refresh_job


# ------------------------------------------------------------- canonicalisation

def test_integral_floats_survive_a_javascript_round_trip():
    """Python writes 7036.0, JavaScript writes 7036. Same number, same digest."""
    server = {"total_kwh": 7036.0, "usage_by_hour": [0.0, 1.5, 2.0]}
    # What comes back after the browser has parsed and re-serialised it.
    browser = json.loads('{"total_kwh": 7036, "usage_by_hour": [0, 1.5, 2]}')

    assert insights.report_key(server) == insights.report_key(browser)
    assert insights.ask_key("why?", server) == insights.ask_key("why?", browser)


def test_booleans_are_not_mangled_into_ints():
    """bool subclasses int; a naive numeric canonicaliser turns True into 1."""
    slim = insights._slim({"sample": True, "other": False})
    assert slim["sample"] is True
    assert slim["other"] is False


def test_canon_leaves_real_decimals_alone():
    slim = insights._slim({"pct_saving": 8.3, "timing_score": 1.024})
    assert slim["pct_saving"] == 8.3
    assert slim["timing_score"] == 1.024


def test_slim_still_drops_the_bulky_fields():
    stats = {
        "total_kwh": 1.5,
        "monthly": [{"month": "2026-01"}] * 12,
        "worst_days": [{"date": "2026-01-01"}],
        "ai_report": {"summary": "echoed back at us"},
        "ai_available": True,
        "usage_by_hour": [0.1] * 24,
    }
    slim = insights._slim(stats)
    for gone in ("monthly", "worst_days", "ai_report", "ai_available", "usage_by_hour"):
        assert gone not in slim
    assert slim["usage_by_hour_kwh"] == [0.1] * 24


def test_slim_output_is_json_serialisable():
    json.dumps(insights._slim({"a": 1.0, "b": [2.0, 3.5], "c": {"d": 4.0}}))


def test_output_token_cap_is_sent():
    """A truncated reply fails JSON parsing, so the cap must leave real headroom."""
    assert insights.MAX_OUTPUT_TOKENS >= 400


# ----------------------------------------------------------------- cron warm-up

@pytest.fixture
def no_shared_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def shared_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTESTKEYTESTKEYTESTKEY")


def test_warm_up_is_skipped_without_a_key(no_shared_key):
    assert refresh_job.warm_sample_report() == "skipped (no shared key)"


def test_warm_up_generates_once_then_reports_a_hit(shared_key, monkeypatch):
    calls = []

    def fake_generate(prompt, json_mode, user_key=None):
        calls.append(prompt)
        return json.dumps({"summary": "s", "recommendations": ["a", "b", "c"]})

    monkeypatch.setattr(insights, "_generate", fake_generate)
    insights._cache.clear()

    assert refresh_job.warm_sample_report() == "generated"
    assert len(calls) == 1
    # Second run inside the cache lifetime must not spend another call.
    assert refresh_job.warm_sample_report() == "already cached"
    assert len(calls) == 1


def test_warm_up_primes_the_key_the_sample_endpoint_will_look_up(shared_key, monkeypatch):
    """The digest must match what /api/greenbutton/sample echoes via the browser."""
    from loadshift import greenbutton

    monkeypatch.setattr(
        insights,
        "_generate",
        lambda p, json_mode, user_key=None: json.dumps(
            {"summary": "s", "recommendations": ["a", "b", "c"]}
        ),
    )
    insights._cache.clear()
    refresh_job.warm_sample_report()

    # Exactly what the endpoint returns, round-tripped through JSON as the
    # browser would send it back.
    kwh = greenbutton.parse(greenbutton.SAMPLE_PATH.read_bytes())
    served = {**greenbutton.analyze(kwh), "sample": True, "ai_available": True}
    echoed = json.loads(json.dumps(served))

    assert insights.cached_report(echoed) is not None


def test_warm_up_swallows_a_gemini_failure(shared_key, monkeypatch):
    def boom(prompt, json_mode, user_key=None):
        raise insights.InsightsError("quota")

    monkeypatch.setattr(insights, "_generate", boom)
    insights._cache.clear()
    assert refresh_job.warm_sample_report().startswith("failed:")


def test_a_failed_warm_up_does_not_change_the_cron_exit_code(shared_key, monkeypatch):
    monkeypatch.setattr(refresh_job.cache, "refresh", lambda: True)
    monkeypatch.setattr(refresh_job, "warm_sample_report", lambda: "failed: boom")
    assert refresh_job.run() is True
