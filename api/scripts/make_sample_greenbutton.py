"""Generate synthetic but realistic 12-month hourly Green Button (ESPI) files.

Usage: make_sample_greenbutton.py [base|ev]
  base -> samples/sample_greenbutton.xml       (~7,000 kWh/yr household)
  ev   -> samples/demo_upload_greenbutton.xml  (~9,500 kWh/yr, evening EV charging)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import config

PROFILE = sys.argv[1] if len(sys.argv) > 1 else "base"
rng = np.random.default_rng(42 if PROFILE == "base" else 7)
end = pd.Timestamp("2026-08-01")
idx = pd.date_range(end - pd.DateOffset(months=12), end, freq="h", inclusive="left")

local = idx.tz_localize("UTC").tz_convert("America/Toronto")
h, dow, m = local.hour.to_numpy(), local.dayofweek.to_numpy(), local.month.to_numpy()

base = 0.35
morning = 0.5 * np.exp(-0.5 * ((h - 7.5) / 1.5) ** 2)
evening = 0.9 * np.exp(-0.5 * ((h - 19) / 2.0) ** 2)
weekend = np.where(dow >= 5, 0.15, 0)
seasonal = 0.45 * np.isin(m, [6, 7, 8]) * np.exp(-0.5 * ((h - 16) / 4) ** 2)  # AC
kw = base + morning + evening + weekend + seasonal + rng.gamma(2, 0.05, len(idx))
if PROFILE == "ev":
    # EV charged at the evening peak (~7.2 kW Level 2, ~2h, most weekdays) —
    # the worst-case habit this product exists to fix.
    charging_day = rng.random(len(idx) // 24).repeat(24)[: len(idx)] < 0.75
    ev = 7.2 * np.isin(h, [19, 20]) * (dow < 5) * charging_day
    kw = kw + ev * rng.uniform(0.85, 1.0, len(idx))
wh = (kw * 1000).round().astype(int)

epoch = ((idx - pd.Timestamp(0)) // pd.Timedelta(seconds=1)).astype(int)  # unit-safe
parts = ['<?xml version="1.0" encoding="UTF-8"?>\n'
         '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:espi="http://naesb.org/espi">\n'
         '<title>Sample Green Button - synthetic Ontario household</title>\n'
         '<entry><content><espi:IntervalBlock>']
for e, v in zip(epoch, wh):
    parts.append(f'<espi:IntervalReading><espi:timePeriod><espi:duration>3600</espi:duration>'
                 f'<espi:start>{e}</espi:start></espi:timePeriod>'
                 f'<espi:value>{v}</espi:value></espi:IntervalReading>')
parts.append('</espi:IntervalBlock></content></entry></feed>')

name = "sample_greenbutton.xml" if PROFILE == "base" else "demo_upload_greenbutton.xml"
out = config.SAMPLES / name
out.parent.mkdir(exist_ok=True)
out.write_text("".join(parts))
print(f"{len(idx)} hourly readings, {out.stat().st_size//1024} KB -> {out}")
