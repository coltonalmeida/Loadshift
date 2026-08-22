"""Parser invariants. Uses files cached in api/data/ by earlier pipeline runs."""
import pandas as pd
import pytest

from loadshift import config, ieso


def test_fuel_mix_namespace_and_shape():
    df = ieso.fuel_mix_year(2024)  # cached
    assert list(df.columns) == config.FUELS
    assert len(df) >= 8784  # leap year
    assert df["NUCLEAR"].max() > 5000  # sane MW scale


def test_hour_1_24_to_utc():
    # IESO hour 1 on 2024-01-01 (EST) == 05:00 UTC; hour 24 == next day 04:00 UTC.
    df = ieso.demand_year(2024)
    assert df.index.min() == pd.Timestamp("2024-01-01 05:00:00")
    day1 = df.loc["2024-01-01 05:00":"2024-01-02 04:00"]
    assert len(day1) == 24


def test_demand_csv_columns():
    df = ieso.demand_year(2024)
    assert list(df.columns) == ["market_demand", "ontario_demand"]
    assert (df["market_demand"] >= df["ontario_demand"]).mean() > 0.99


def test_dataset_hourly_and_dense():
    p = config.DATA / "dataset.parquet"
    if not p.exists():
        pytest.skip("run scripts/build_dataset.py first")
    df = pd.read_parquet(p)
    steps = df.index.to_series().diff().dropna()
    assert (steps == pd.Timedelta(hours=1)).all()
    assert df[["net_demand", "avg_intensity"]].notna().all().all()


def test_pricing_tou_windows():
    from loadshift import pricing
    # Thu 2026-08-20 (summer weekday): 13:00 local = 17:00 UTC -> on-peak
    assert pricing.rate_cents(pd.Timestamp("2026-08-20 17:00")) == 20.3
    # 20:00 local -> off-peak
    assert pricing.rate_cents(pd.Timestamp("2026-08-21 00:00")) == 9.8
    # Sat all day off-peak
    assert pricing.rate_cents(pd.Timestamp("2026-08-22 16:00")) == 9.8
    # Canada Day (Wed 2026-07-01) noon -> holiday off-peak
    assert pricing.rate_cents(pd.Timestamp("2026-07-01 16:00")) == 9.8
    # Winter weekday 08:00 local -> on-peak
    assert pricing.rate_cents(pd.Timestamp("2026-01-15 13:00")) == 20.3


def test_pricing_ulo():
    from loadshift import pricing
    # 02:00 local any day -> ultra-low
    assert pricing.rate_cents(pd.Timestamp("2026-08-20 06:00"), "ulo") == 3.9
    # weekday 18:00 local -> ULO on-peak
    assert pricing.rate_cents(pd.Timestamp("2026-08-20 22:00"), "ulo") == 39.1


def test_limiter_allowance_and_recovery():
    """A client gets its stated allowance, then 429s until the window lapses."""
    from loadshift.ratelimit import Limiter

    lim = Limiter(per_client=3, window_s=600, daily=100)
    seen = []
    for _ in range(3):
        ok, _remaining, _retry = lim.check("1.2.3.4")
        assert ok
        seen.append(lim.consume("1.2.3.4"))
    assert seen == [2, 1, 0]

    ok, remaining, retry = lim.check("1.2.3.4")
    assert not ok and remaining == 0 and retry > 0

    # A different caller is unaffected: the budget is per client, not global.
    ok, remaining, _ = lim.check("5.6.7.8")
    assert ok and remaining == 3


def test_limiter_daily_cap_spans_clients():
    from loadshift.ratelimit import Limiter

    lim = Limiter(per_client=10, window_s=600, daily=2)
    lim.consume("a")
    lim.consume("b")
    ok, remaining, retry = lim.check("c")
    assert not ok and remaining == 0 and retry > 0


def test_limiter_check_does_not_consume():
    """Cache hits call check/remaining; neither may spend the allowance."""
    from loadshift.ratelimit import Limiter

    lim = Limiter(per_client=2, window_s=600, daily=100)
    for _ in range(5):
        assert lim.check("x")[0] is True
        assert lim.remaining("x") == 2
