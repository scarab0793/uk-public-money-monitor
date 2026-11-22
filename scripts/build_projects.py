#!/usr/bin/env python3
"""Convert a source-attributed project CSV into the static searchable catalogue.

Usage: python scripts/build_projects.py path/to/official-projects.csv
The input must contain the canonical columns documented in docs/project-import.md.
Never manufacture missing baseline values or source URLs.
"""
import csv
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "projects.json"
COLUMNS = {"id", "name", "department", "sector", "status", "source_url",
           "source_title", "source_as_of"}
NUMERIC = ("original_budget_gbp", "current_forecast_gbp", "actual_spend_gbp")
DATES = ("original_completion", "forecast_completion", "actual_completion")

def parse_amount(raw):
    if raw is None or not raw.strip():
        return None
    value = float(raw.replace(",", "").strip())
    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid project amount")
    return value

def parse_date(raw):
    if not raw or not raw.strip():
        return None
    return date.fromisoformat(raw.strip()).isoformat()

def validate(row, line):
    missing = [c for c in COLUMNS if not (row.get(c) or "").strip()]
    if missing:
        raise ValueError(f"Row {line}: missing {', '.join(sorted(missing))}")
    url = urlparse(row["source_url"])
    if url.scheme != "https" or not url.hostname:
        raise ValueError(f"Row {line}: source_url must be HTTPS")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", row["id"].strip()):
        raise ValueError(f"Row {line}: invalid ID")
    result = {key: row[key].strip() for key in COLUMNS}
    result["source_as_of"] = parse_date(row["source_as_of"])
    for key in NUMERIC:
        result[key] = parse_amount(row.get(key))
    for key in DATES:
        result[key] = parse_date(row.get(key))
    result["nation"] = (row.get("nation") or "").strip()
    result["description"] = (row.get("description") or "").strip()
    result["notes"] = (row.get("notes") or "").strip()
    return result

def build(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError("Missing required CSV headers")
        projects = []
        seen = set()
        for line, row in enumerate(reader, start=2):
            project = validate(row, line)
            if project["id"] in seen:
                raise ValueError(f"Row {line}: duplicate project ID")
            seen.add(project["id"])
            projects.append(project)
    projects.sort(key=lambda p: p["name"].casefold())
    payload = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
               "project_count": len(projects), "projects": projects}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(OUT)
    print(f"Published {len(projects)} source-attributed projects")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/build_projects.py <csv>")
    build(Path(sys.argv[1]))
