#!/usr/bin/env python3
"""Derive calendar and UK fiscal-year summaries from validated ONS monthly data."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
INPUT = ROOT / "data/ons-public-finances.json"


def summarize(payload, fiscal=False):
    result = {
        "schema_version": 1,
        "publisher": "Office for National Statistics",
        "generated_from": payload.get("retrieved_at"),
        "year_definition": "UK financial year: 1 April to 31 March" if fiscal else "Calendar year: 1 January to 31 December",
        "note": "ANBV/ANLP measure central government CURRENT receipts/expenditure, not total public sector income/spending. Do not subtract them to infer fiscal deficit. HF6X is a debt ratio, not a sum. Incomplete years are flagged.",
        "series": {},
    }
    for code, series in payload["series"].items():
        groups = {}
        for observation in series["observations"]:
            year_str, month_str = observation["period"].split()
            year, month = int(year_str), MONTHS[month_str]
            start = year - (1 if fiscal and month <= 3 else 0)
            key = f"{start}-{str((start + 1) % 100).zfill(2)}" if fiscal else str(start)
            groups.setdefault(key, []).append((year, month, observation))
        annual = []
        for key, items in sorted(groups.items()):
            items.sort(key=lambda x: (x[0], x[1]))
            months = {(y, m) for y, m, _ in items}
            if len(months) != len(items):
                raise ValueError(f"Duplicate monthly observation in {code}: {key}")
            debt = code.lower() == "hf6x"
            value = items[-1][2]["value"] if debt else round(sum(x[2]["value"] for x in items) * 1_000_000)
            entry = {
                ("financial_year" if fiscal else "year"): key,
                "months": len(items),
                "complete": len(items) == 12,
                "value": value,
                "unit": "% GDP" if debt else "GBP",
                "method": "last available monthly observation" if debt else "sum of available monthly observations",
                "last_period": items[-1][2]["period"],
            }
            if fiscal:
                entry["period_start"] = items[0][2]["period"]
                entry["period_end"] = items[-1][2]["period"]
            annual.append(entry)
        result["series"][code] = {
            "label": series["label"],
            "source": series["source"],
            ("years" if fiscal else "annual"): annual,
        }
    return result


def main():
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    for fiscal, filename in ((False, "ons-calendar-year-summary.json"), (True, "ons-financial-year-summary.json")):
        output = summarize(payload, fiscal=fiscal)
        target = ROOT / "data" / filename
        target.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {filename}: {sum(len(s['years' if fiscal else 'annual']) for s in output['series'].values())} annual observations")


if __name__ == "__main__":
    main()
