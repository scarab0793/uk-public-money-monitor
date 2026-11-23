#!/usr/bin/env python3
"""Build month-aligned year-over-year comparisons from validated ONS series."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


def build(payload):
    by_period = {}
    for code, series in payload["series"].items():
        for observation in series["observations"]:
            period = observation["period"]
            by_period.setdefault(period, {"period": period})[code] = observation["value"]
    def key(period):
        year, month = period.split()
        return int(year), MONTHS[month]
    months = []
    for period in sorted(by_period, key=key):
        record = dict(by_period[period])
        year, month = period.split()
        previous = by_period.get(f"{int(year)-1} {month}", {})
        for code in ("anbv", "anlp", "hf6x"):
            if code not in record:
                continue
            if code != "hf6x":
                record[code + "_gbp"] = round(record[code] * 1_000_000)
            if code in previous:
                delta = record[code] - previous[code]
                record[code + "_yoy_change"] = round(delta, 2) if code == "hf6x" else round(delta * 1_000_000)
                if code != "hf6x" and previous[code] != 0:
                    record[code + "_yoy_percent"] = round(delta / previous[code] * 100, 2)
        months.append(record)
    return {
        "schema_version": 1,
        "source": "ONS Public Sector Finances monthly series HF6X, ANBV, ANLP",
        "source_retrieved_at": payload.get("retrieved_at"),
        "notes": "ANBV and ANLP are central government CURRENT receipts and expenditure; not total taxes or total public spending. Year-on-year changes compare the same month in the previous year. HF6X change is in percentage points. Monetary values converted from GBP million to GBP.",
        "count": len(months),
        "months": months,
    }


def main():
    payload = json.loads((ROOT / "data/ons-public-finances.json").read_text(encoding="utf-8"))
    output = build(payload)
    (ROOT / "data/ons-monthly-comparisons.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("Built", output["count"], "monthly comparison records")


if __name__ == "__main__":
    main()
