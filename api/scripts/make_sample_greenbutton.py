"""Generate a synthetic but realistic 12-month hourly Green Button (ESPI) file."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

rng = np.random.default_rng(42)
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

out = Path(__file__).resolve().parents[1] / "samples" / "sample_greenbutton.xml"
out.parent.mkdir(exist_ok=True)
out.write_text("".join(parts))
print(f"{len(idx)} hourly readings, {out.stat().st_size//1024} KB -> {out}")
