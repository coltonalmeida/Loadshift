"""Hit all four upstream data sources and print row counts. Run at the start of every phase."""
import datetime
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loadshift import config


def check(name, fn):
    try:
        detail = fn()
        print(f"  OK   {name}: {detail}")
        return True
    except Exception as e:  # noqa: BLE001 - smoke script reports anything
        print(f"  FAIL {name}: {type(e).__name__}: {e}")
        return False


def gen_capability():
    r = requests.get(config.GEN_CAPABILITY_URL, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"n": config.NS_CAPABILITY}
    gens = root.findall(".//n:Generator", ns)
    assert gens, "no <Generator> elements — namespace changed?"
    return f"{len(gens)} generators, {len(r.content)//1024} KB"


def gen_by_fuel():
    year = datetime.date.today().year
    r = requests.get(config.GEN_BY_FUEL_URL.format(year=year), timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"n": config.NS_BY_FUEL}
    days = root.findall(".//n:DailyData", ns)
    assert days, "no <DailyData> elements — namespace changed?"
    return f"{len(days)} days in {year}, {len(r.content)//1024} KB"


def demand():
    year = datetime.date.today().year
    r = requests.get(config.DEMAND_URL.format(year=year), timeout=30)
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    header = lines[3]
    assert "Ontario Demand" in header, f"unexpected header: {header!r}"
    return f"{len(lines) - 4} hourly rows in {year}"


def weather():
    r = requests.get(config.OPEN_METEO_FORECAST.format(days=2), timeout=30)
    r.raise_for_status()
    hours = r.json()["hourly"]["time"]
    r2 = requests.get(
        config.OPEN_METEO_ARCHIVE.format(start="2024-01-01", end="2024-01-02"), timeout=30
    )
    r2.raise_for_status()
    hist = r2.json()["hourly"]["time"]
    return f"forecast {len(hours)}h, archive {len(hist)}h"


if __name__ == "__main__":
    print("Smoke-testing upstream sources:")
    results = [
        check("IESO GenOutputCapability (live)", gen_capability),
        check("IESO GenOutputbyFuelHourly (history)", gen_by_fuel),
        check("IESO Demand CSV", demand),
        check("Open-Meteo forecast + archive", weather),
    ]
    sys.exit(0 if all(results) else 1)
