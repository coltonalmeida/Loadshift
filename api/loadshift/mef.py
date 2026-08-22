"""Marginal emissions factor via delta regression (Siler-Evans, Azevedo & Morgan 2012).

Per bucket (season x hour-block), within overlapping net-demand quantile windows:
    OLS slope_f = cov(dGen_f, dDemand) / var(dDemand)   [MW fuel f per MW load]
    MEF(window) = sum_f slope_f * EF_f                    [gCO2eq/kWh]
Linear interpolation between window centres gives a smooth MEF(bucket, net_demand)
curve. Intertie flows are not modelled, so sum_f slope_f != 1; we report it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, dataset

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"

N_CENTERS = 19          # window centres at quantiles 0.05 .. 0.95
HALF_WIDTH = 0.125      # each window spans +/- 12.5 quantile points (overlapping)
MIN_WINDOW_N = 80  # up-deltas halve the sample      # skip windows with fewer delta observations


def _deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Hour-over-hour deltas with the bucket/net-demand of the later hour."""
    d = pd.DataFrame(index=df.index)
    for f in config.FUELS:
        d[f"d_{f}"] = df[f].diff()
    d["d_demand"] = df["ontario_demand"].diff()
    d["net_demand"] = df["net_demand"]
    d["bucket"] = dataset.bucket_of(df)
    d = d.dropna()
    # Up-deltas only: the product question is "what turns ON for an added kWh".
    # Pooling down-deltas contaminates overnight hours with the evening gas
    # rampdown (gas tracks demand downward even when it could not ramp up).
    return d[d["d_demand"] > 0]


def fit(df: pd.DataFrame) -> dict:
    """Fit the MEF curve. Returns the mef_curve.json payload."""
    d = _deltas(df)
    curves: dict[str, dict] = {}
    centers_q = np.linspace(0.05, 0.95, N_CENTERS)

    for bucket, grp in d.groupby("bucket"):
        nd = grp["net_demand"]
        rows = []
        for q in centers_q:
            lo, hi = nd.quantile(max(q - HALF_WIDTH, 0)), nd.quantile(min(q + HALF_WIDTH, 1))
            w = grp[(nd >= lo) & (nd <= hi)]
            if len(w) < MIN_WINDOW_N:
                continue
            var = w["d_demand"].var()
            if var == 0:
                continue
            slopes = {
                f: float(w[f"d_{f}"].cov(w["d_demand"]) / var) for f in config.FUELS
            }
            mef = sum(slopes[f] * config.EMISSION_FACTORS[f] for f in config.FUELS)
            # R^2 of the total-generation response (how much of dDemand the
            # modelled fleet explains)
            d_gen = sum(w[f"d_{f}"] for f in config.FUELS)
            r2 = float(d_gen.corr(w["d_demand"]) ** 2)
            rows.append({
                "nd": float(nd.quantile(q)),
                "mef": float(mef),
                "sum_slope": float(sum(slopes.values())),
                "gas_slope": slopes["GAS"],
                "r2": r2,
                "n": int(len(w)),
            })
        if not rows:
            # Sparse bucket (few up-deltas, e.g. evening rampdown): one OLS
            # over the whole bucket, constant in net demand.
            var = grp["d_demand"].var()
            slopes = {f: float(grp[f"d_{f}"].cov(grp["d_demand"]) / var) for f in config.FUELS}
            mef_v = sum(slopes[f] * config.EMISSION_FACTORS[f] for f in config.FUELS)
            d_gen = sum(grp[f"d_{f}"] for f in config.FUELS)
            rows = [{"nd": float(nd.median()), "mef": float(mef_v),
                     "sum_slope": float(sum(slopes.values())), "gas_slope": slopes["GAS"],
                     "r2": float(d_gen.corr(grp["d_demand"]) ** 2), "n": int(len(grp))}]
        if rows:
            curves[bucket] = {
                "nd": [r["nd"] for r in rows],
                "mef": [r["mef"] for r in rows],
                "sum_slope": [r["sum_slope"] for r in rows],
                "gas_slope": [r["gas_slope"] for r in rows],
                "r2": [r["r2"] for r in rows],
                "n": [r["n"] for r in rows],
            }
    return {
        "method": "delta-OLS per season x hour-block, overlapping net-demand windows",
        "citation": "Siler-Evans, Azevedo & Morgan (2012), ES&T 46(9)",
        "emission_factors": config.EMISSION_FACTORS,
        "train_start": str(df.index.min()),
        "train_end": str(df.index.max()),
        "curves": curves,
    }


class MefCurve:
    """Evaluate MEF(bucket, net_demand) from a fitted curve payload."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.curves = payload["curves"]

    @classmethod
    def load(cls, path: Path | None = None) -> "MefCurve":
        p = path or ARTIFACTS / "mef_curve.json"
        return cls(json.loads(p.read_text()))

    def mef(self, bucket: str, net_demand: float) -> float:
        c = self.curves[bucket]
        return float(np.interp(net_demand, c["nd"], c["mef"]))

    def label(self, df: pd.DataFrame) -> pd.Series:
        """MEF label for every row of a dataset frame."""
        buckets = dataset.bucket_of(df)
        out = np.empty(len(df))
        for b, idx in buckets.groupby(buckets).groups.items():
            c = self.curves[b]
            out[df.index.get_indexer(idx)] = np.interp(
                df.loc[idx, "net_demand"].to_numpy(), c["nd"], c["mef"]
            )
        return pd.Series(out, index=df.index, name="mef")


def save(payload: dict) -> Path:
    ARTIFACTS.mkdir(exist_ok=True)
    p = ARTIFACTS / "mef_curve.json"
    p.write_text(json.dumps(payload, indent=1))
    return p
