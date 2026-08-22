"""Build the hourly training dataset -> data/dataset.parquet, print QA summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import dataset

if __name__ == "__main__":
    df = dataset.build()
    out = Path(__file__).resolve().parents[1] / "data" / "dataset.parquet"
    df.to_parquet(out)

    print(f"rows: {len(df)}   {df.index.min()} -> {df.index.max()} (UTC)")
    print(f"columns: {list(df.columns)}")
    gaps = df.index.to_series().diff().dt.total_seconds().div(3600).sub(1).abs().gt(0.01).sum()
    print(f"index gaps (non-hourly steps): {gaps}")
    nn = df.isna().sum()
    print("NaNs per column (nonzero only):")
    print(nn[nn > 0].to_string() if nn.any() else "  none")
    print(f"\navg_intensity: min {df['avg_intensity'].min():.1f}  "
          f"mean {df['avg_intensity'].mean():.1f}  max {df['avg_intensity'].max():.1f} gCO2/kWh")
    print(f"saved -> {out}")
