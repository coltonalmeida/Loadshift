"""Validation only: compare our AVERAGE intensity against Electricity Maps (Ontario).

Usage: set ELECTRICITYMAPS_TOKEN, then run. We do not build on this API —
it is a one-time sanity check for the README/video credibility line.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TOKEN = os.environ.get("ELECTRICITYMAPS_TOKEN")
if not TOKEN:
    sys.exit("set ELECTRICITYMAPS_TOKEN (free tier: https://api-portal.electricitymaps.com)")

r = requests.get(
    "https://api.electricitymaps.com/v4/carbon-intensity/history",
    params={"zone": "CA-ON"}, headers={"auth-token": TOKEN}, timeout=30,
)
r.raise_for_status()
em = pd.DataFrame(r.json()["history"])
em["ts"] = pd.to_datetime(em["datetime"]).dt.tz_localize(None)
em = em.set_index("ts")["carbonIntensity"]

ours = pd.read_parquet(Path(__file__).resolve().parents[1] / "artifacts" / "mef_history.parquet")
joined = ours[["avg_intensity"]].join(em.rename("em"), how="inner").dropna()
if joined.empty:
    sys.exit("no overlapping hours returned")
diff = joined["avg_intensity"] - joined["em"]
print(f"overlap: {len(joined)} hours ({joined.index.min()} -> {joined.index.max()})")
print(f"ours mean {joined['avg_intensity'].mean():.1f} g, EM mean {joined['em'].mean():.1f} g")
print(f"MAE {diff.abs().mean():.1f} g, bias {diff.mean():+.1f} g, "
      f"corr {joined['avg_intensity'].corr(joined['em']):.2f}")
