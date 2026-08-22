"""Parser invariants. Uses files cached in api/data/ by earlier pipeline runs."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import config, dataset, ieso


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
    p = Path(__file__).resolve().parents[1] / "data" / "dataset.parquet"
    if not p.exists():
        pytest.skip("run scripts/build_dataset.py first")
    df = pd.read_parquet(p)
    steps = df.index.to_series().diff().dropna()
    assert (steps == pd.Timedelta(hours=1)).all()
    assert df[["net_demand", "avg_intensity"]].notna().all().all()
