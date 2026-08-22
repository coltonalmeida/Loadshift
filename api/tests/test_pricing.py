"""Ontario RPP rate classification, and the holiday calendar it depends on.

A holiday is off-peak under Time-of-Use and daytime-rate under Ultra-Low
Overnight, so getting one wrong quietly reprices every hour of that day in the
Green Button analysis. Victoria Day is the one that needs a test: it is the only
Ontario holiday defined by "the Monday on or before" a date rather than an nth
weekday, and the arithmetic is easy to get wrong in exactly the years where
May 24 is itself a Monday.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from loadshift import pricing


def test_victoria_day_is_the_monday_on_or_before_may_24():
    # 2027 and 2032 are the trap: May 24 is itself a Monday, so it IS the
    # holiday and the answer is not the Monday of the week before.
    expected = {
        2024: dt.date(2024, 5, 20),
        2025: dt.date(2025, 5, 19),
        2026: dt.date(2026, 5, 18),
        2027: dt.date(2027, 5, 24),
        2028: dt.date(2028, 5, 22),
        2032: dt.date(2032, 5, 24),
    }
    for year, day in expected.items():
        got = pricing._victoria_day(year)
        assert got == day, f"{year}: got {got}, want {day}"
        assert got.weekday() == pricing.MONDAY
        assert dt.date(year, 5, 18) <= got <= dt.date(year, 5, 24)
        assert pricing.is_holiday(got)


def test_statutory_holidays_and_ordinary_days():
    assert pricing.is_holiday(dt.date(2026, 1, 1))    # New Year's Day
    assert pricing.is_holiday(dt.date(2026, 2, 16))   # Family Day, 3rd Mon Feb
    assert pricing.is_holiday(dt.date(2026, 4, 3))    # Good Friday, lookup table
    assert pricing.is_holiday(dt.date(2026, 9, 7))    # Labour Day, 1st Mon Sep
    assert pricing.is_holiday(dt.date(2026, 12, 26))  # Boxing Day
    assert not pricing.is_holiday(dt.date(2026, 5, 19))
    assert not pricing.is_holiday(dt.date(2027, 5, 17))


def _hour(local: str) -> pd.Timestamp:
    """A naive-UTC timestamp for a local America/Toronto wall-clock hour."""
    return (
        pd.Timestamp(local)
        .tz_localize(pricing.TZ)
        .tz_convert("UTC")
        .tz_localize(None)
    )


def test_tou_holiday_is_off_peak_all_day():
    # A summer weekday noon is on-peak; the same hour on Victoria Day is not.
    assert pricing.rate_cents(_hour("2027-05-25 12:00")) == pricing.TOU_RATES["on"]
    assert pricing.rate_cents(_hour("2027-05-24 12:00")) == pricing.TOU_RATES["off"]


def test_ulo_overnight_is_cheapest_and_holiday_daytime_is_not_on_peak():
    assert pricing.rate_cents(_hour("2027-05-24 02:00"), "ulo") == pricing.ULO_RATES["ulo"]
    # 5 PM on a weekday is the 39.1c window; on the holiday it is the day rate.
    assert pricing.rate_cents(_hour("2027-05-25 17:00"), "ulo") == pricing.ULO_RATES["on"]
    assert pricing.rate_cents(_hour("2027-05-24 17:00"), "ulo") == pricing.ULO_RATES["day"]


def test_window_cost_spreads_energy_over_the_hours_it_runs():
    start = _hour("2027-05-24 01:00")  # entirely inside the ULO window
    assert pricing.window_cost_cents(4.0, start, 4, "ulo") == round(4.0 * 3.9, 1)
