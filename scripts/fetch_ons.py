#!/usr/bin/env python3
"""Fetch and validate ONS public-finance time series. Never replace good data on failure."""
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.ons.gov.uk/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries"
SERIES = {
    "hf6x": {"label": "Public sector net debt excluding public sector banks", "unit": "% of GDP", "min": 0, "max": 300},
    "anbv": {"label": "Central government current receipts", "unit": "GBP million", "min": -100000, "max": 1000000},
    "anlp": {"label": "Central government current expenditure", "unit": "GBP million", "min": -100000, "max": 1000000},
}
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "ons-public-finances.json"

def get_series(code):
    url = f"{BASE}/{code}/dataset/pusf/data"
    req = urllib.request.Request(url, headers={"User-Agent": "UKPublicMoneyMonitor/0.2 (+https://github.com/scarab0793/uk-public-money-monitor)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    # ONS time series response provides months with year, month, value.
    months = payload.get("months")
    if not isinstance(months, list) or len(months) < 12:
        raise ValueError(f"Unexpected or incomplete ONS monthly data for {code}")
    observations = []
    for row in months:
        date = row.get("date")
        value = row.get("value")
        if not isinstance(date, str) or not re.fullmatch(r"\d{4} [A-Z]{3}", date):
            continue
        try:
            number = float(str(value).replace(",", ""))
        except (ValueError, TypeError):
            continue
        if not SERIES[code]["min"] <= number <= SERIES[code]["max"] :
            raise ValueError(f"Unexpected percentage value {number} at {date}")
        observations.append({"period": date, "value": number})
    if len(observations) < 12:
        raise ValueError("Not enough valid observations")
    # The ONS API may return newest-first. Sort by calendar month before
    # publishing so the dashboard's final observation is truly the latest.
    month_numbers = {name: i for i, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}
    def period_key(row):
        year, month = row["period"].split()
        if month not in month_numbers:
            raise ValueError(f"Invalid month: {month}")
        return int(year), month_numbers[month]
    observations.sort(key=period_key)
    if len({row["period"] for row in observations}) != len(observations):
        raise ValueError("Duplicate monthly observations")
    return {"label": SERIES[code]["label"], "unit": SERIES[code]["unit"], "source": url, "series_code": code.upper(), "observations": observations}

def main():
    result = {"publisher": "Office for National Statistics", "dataset": "PUSF", "retrieved_at": datetime.now(timezone.utc).isoformat(), "series": {}}
    for code in SERIES:
        result["series"][code] = get_series(code)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print("Updated", OUT)

if __name__ == "__main__":
    main()
