"""Ontario Regulated Price Plan rates (OEB, effective 2025-11-01).

Source: oeb.ca "Electricity rates". Two plans:
  TOU  - off-peak 9.8, mid-peak 15.7, on-peak 20.3 cents/kWh
         winter (Nov-Apr) weekdays: on-peak 7-11 & 17-19, mid-peak 11-17
         summer (May-Oct) weekdays: on-peak 11-17, mid-peak 7-11 & 17-19
         nights 19-07, weekends and holidays: off-peak
  ULO  - ultra-low 3.9 (every day 23-07), weekday mid-peak 15.7 (07-16 & 21-23),
         weekday on-peak 39.1 (16-21), weekend/holiday daytime 9.8 (07-23)

Holidays follow the Ontario RPP holiday schedule (fixed-date list plus
weekday-rule holidays; Good Friday from a small lookup table).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("America/Toronto")

TOU_RATES = {"off": 9.8, "mid": 15.7, "on": 20.3}
ULO_RATES = {"ulo": 3.9, "day": 9.8, "mid": 15.7, "on": 39.1}
RATES_EFFECTIVE = "2025-11-01"

GOOD_FRIDAY = {2024: (3, 29), 2025: (4, 18), 2026: (4, 3), 2027: (3, 26)}


MONDAY = 0


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """The nth `weekday` of a month, e.g. the 3rd Monday of February."""
    d = dt.date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + dt.timedelta(days=offset + 7 * (n - 1))


def _victoria_day(year: int) -> dt.date:
    """The Monday on or before May 24."""
    d = dt.date(year, 5, 24)
    return d - dt.timedelta(days=d.weekday())


def is_holiday(d: dt.date) -> bool:
    y = d.year
    fixed = {(1, 1), (7, 1), (12, 25), (12, 26)}
    if (d.month, d.day) in fixed:
        return True
    if y in GOOD_FRIDAY and (d.month, d.day) == GOOD_FRIDAY[y]:
        return True
    holidays = {
        _nth_weekday(y, 2, MONDAY, 3),   # Family Day
        _victoria_day(y),                # Victoria Day
        _nth_weekday(y, 8, MONDAY, 1),   # Civic Holiday
        _nth_weekday(y, 9, MONDAY, 1),   # Labour Day
        _nth_weekday(y, 10, MONDAY, 2),  # Thanksgiving
    }
    return d in holidays


def rate_cents(ts_utc: pd.Timestamp, plan: str = "tou") -> float:
    """Rate in cents/kWh for the hour starting at ts_utc (naive UTC)."""
    local = ts_utc.tz_localize("UTC").tz_convert(TZ) if ts_utc.tzinfo is None else ts_utc.tz_convert(TZ)
    h, date = local.hour, local.date()
    weekend = local.weekday() >= 5 or is_holiday(date)

    if plan == "ulo":
        if h >= 23 or h < 7:
            return ULO_RATES["ulo"]
        if weekend:
            return ULO_RATES["day"]
        if 16 <= h < 21:
            return ULO_RATES["on"]
        return ULO_RATES["mid"]

    # TOU
    if weekend or h >= 19 or h < 7:
        return TOU_RATES["off"]
    summer = 5 <= local.month <= 10
    midday = 11 <= h < 17
    if summer:
        return TOU_RATES["on"] if midday else TOU_RATES["mid"]
    return TOU_RATES["mid"] if midday else TOU_RATES["on"]


def series_rates(index: pd.DatetimeIndex, plan: str = "tou") -> pd.Series:
    return pd.Series([rate_cents(ts, plan) for ts in index], index=index)


def window_cost_cents(kwh: float, start_utc: pd.Timestamp, duration_h: int,
                      plan: str = "tou") -> float:
    """Cost of running kwh spread evenly over duration_h hours from start."""
    hours = pd.date_range(start_utc, periods=duration_h, freq="h")
    per_hour = kwh / duration_h
    return round(sum(rate_cents(ts, plan) * per_hour for ts in hours), 1)
