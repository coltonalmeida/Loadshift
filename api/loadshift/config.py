"""Shared constants: paths, URLs, namespaces, emission factors, coordinates."""
from pathlib import Path

# The api/ directory. Every path below hangs off it, so the layout is described
# in one place instead of being rebuilt with parents[1] in each module.
ROOT = Path(__file__).resolve().parents[1]

# Committed model artifacts. Named here, not in model.py, so the web service can
# name the directory without importing LightGBM — only the cron job trains or
# predicts, and that import costs ~150MB of RSS in a process that never uses it.
ARTIFACTS = ROOT / "artifacts"

# Raw downloads and the on-disk cache tier. Ephemeral: gitignored, and wiped by
# every Render deploy, which is why Key Value is the durable tier.
DATA = ROOT / "data"

# Bundled Green Button files backing the "Try sample data" path.
SAMPLES = ROOT / "samples"

IESO_BASE = "https://reports-public.ieso.ca/public"

# Live per-generator output (namespace differs from the historical report!)
GEN_CAPABILITY_URL = f"{IESO_BASE}/GenOutputCapability/PUB_GenOutputCapability.xml"
NS_CAPABILITY = "http://www.theIMO.com/schema"

# Historical hourly generation by fuel type, one file per year (2022+)
GEN_BY_FUEL_URL = f"{IESO_BASE}/GenOutputbyFuelHourly/PUB_GenOutputbyFuelHourly_{{year}}.xml"
NS_BY_FUEL = "http://www.ieso.ca/schema"

# Hourly Ontario demand CSV, one file per year (2024+ only)
DEMAND_URL = f"{IESO_BASE}/Demand/PUB_Demand_{{year}}.csv"

# Open-Meteo (no key). Coordinates: Mississauga / GTA load centre.
LAT, LON = 43.59, -79.64
WEATHER_VARS = "temperature_2m,wind_speed_100m,cloud_cover,shortwave_radiation"
OPEN_METEO_ARCHIVE = (
    "https://archive-api.open-meteo.com/v1/archive"
    f"?latitude={LAT}&longitude={LON}&hourly={WEATHER_VARS}"
    "&timezone=America%2FToronto&start_date={start}&end_date={end}"
)
OPEN_METEO_FORECAST = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}&hourly={WEATHER_VARS}"
    "&timezone=America%2FToronto&forecast_days={days}"
)

TIMEZONE = "America/Toronto"

# Training window: demand CSVs only exist 2024+.
TRAIN_START = "2024-01-01"

FUELS = ["NUCLEAR", "GAS", "HYDRO", "WIND", "SOLAR", "BIOFUEL"]

# Lifecycle emission factors, gCO2eq/kWh — IPCC AR5 WGIII Annex III medians.
EMISSION_FACTORS = {
    "GAS": 490,
    "BIOFUEL": 230,
    "SOLAR": 48,
    "HYDRO": 24,
    "NUCLEAR": 12,
    "WIND": 11,
}

# Appliance kWh-per-run defaults (NRCan EnerGuide typical ranges).
APPLIANCE_DEFAULTS = {
    "dryer": {"kwh_range": [1.8, 5.0], "duration_h": 1},
    "dishwasher": {"kwh_range": [0.9, 1.8], "duration_h": 2},
    "washer": {"kwh_range": [0.3, 1.0], "duration_h": 1},
    "ev_charge": {"kwh_range": [7.0, 11.0], "duration_h": 4},
}
