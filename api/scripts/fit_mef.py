"""Fit the MEF curve -> artifacts/mef_curve.json, print QA summary."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import mef

if __name__ == "__main__":
    df = pd.read_parquet(Path(__file__).resolve().parents[1] / "data" / "dataset.parquet")
    payload = mef.fit(df)
    path = mef.save(payload)

    curves = payload["curves"]
    print(f"buckets fitted: {len(curves)}")
    all_mef, all_ss, all_r2, non_mono = [], [], [], 0
    for b, c in sorted(curves.items()):
        m = np.array(c["mef"])
        all_mef += list(m)
        all_ss += c["sum_slope"]
        all_r2 += c["r2"]
        # Spearman-ish monotonicity: correlation of MEF with net demand ordering
        rho = np.corrcoef(np.arange(len(m)), m)[0, 1] if len(m) > 2 else float("nan")
        if rho < 0.5:
            non_mono += 1
        print(f"  {b:<18} nd {c['nd'][0]:>6.0f}-{c['nd'][-1]:>6.0f} MW   "
              f"MEF {m.min():5.1f}-{m.max():5.1f} g   trend r={rho:+.2f}   "
              f"sum_slope~{np.mean(c['sum_slope']):.2f}")
    print(f"\nMEF overall: {min(all_mef):.1f} .. {max(all_mef):.1f} gCO2/kWh "
          f"(mean {np.mean(all_mef):.1f})")
    print(f"mean sum_slope: {np.mean(all_ss):.2f}   mean window R^2: {np.mean(all_r2):.2f}")
    print(f"buckets with weak upward trend (r<0.5): {non_mono}")

    lab = mef.MefCurve(payload).label(df)
    print(f"labelled history: mean {lab.mean():.1f} g, p5 {lab.quantile(.05):.1f}, "
          f"p95 {lab.quantile(.95):.1f}")
    print(f"saved -> {path}")

    # Compact hourly MEF history artifact (Render needs it for Green Button
    # comparisons without shipping the full dataset).
    hist = lab.to_frame()
    hist["avg_intensity"] = df["avg_intensity"]
    hist_path = Path(__file__).resolve().parents[1] / "artifacts" / "mef_history.parquet"
    hist.to_parquet(hist_path)
    print(f"saved -> {hist_path} ({hist_path.stat().st_size//1024} KB)")
