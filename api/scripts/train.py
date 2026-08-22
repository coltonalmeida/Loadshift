"""Train the forecaster -> artifacts/model.txt + model_card.json."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import mef, model

if __name__ == "__main__":
    df = pd.read_parquet(Path(__file__).resolve().parents[1] / "data" / "dataset.parquet")
    label = mef.MefCurve.load().label(df)
    card = model.train(df, label)
    print(f"MAE  model : {card['mae_model']:.2f} g")
    print(f"MAE  naive : {card['mae_baseline_seasonal_naive_168h']:.2f} g  (seasonal naive, t-168h)")
    print(f"improvement: {card['improvement_pct']:.1f}%   test R2: {card['test_r2']}")
    print(f"test window: {card['test_range'][0]} -> {card['test_range'][1]}")
