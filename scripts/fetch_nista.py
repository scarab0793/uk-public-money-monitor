#!/usr/bin/env python3
"""Publish the official NISTA 2024-25 GMPP CSV as searchable source rows.

Never guess column units or reinterpret financial values. Original column/value
pairs are retained verbatim until a reviewed mapping is available.
"""
import csv
import hashlib
import io
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://assets.publishing.service.gov.uk/media/6895fbb63080e72710b2e2ef/nista_annual_report_data_2425.csv"
SOURCE_PAGE = "https://www.gov.uk/government/publications/nista-annual-report-2024-2025"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nista-raw-projects.json"
PROJECTS_OUT = ROOT / "data" / "projects.json"

def build(raw):
    if len(raw) < 1000 or len(raw) > 15_000_000:
        raise ValueError("Unexpected CSV size")
    decoded = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    fields = reader.fieldnames or []
    if len(fields) < 3 or len(set(fields)) != len(fields):
        raise ValueError("Invalid or duplicate CSV headings")
    # Keep original source headings and values unchanged.
    records = []
    for row in reader:
        if not any(str(v or "").strip() for v in row.values()):
            continue
        if None in row:
            raise ValueError("CSV row has more cells than headers")
        records.append({str(k): str(v or "").strip() for k, v in row.items()})
    if not 20 <= len(records) <= 10000:
        raise ValueError(f"Unexpected row count: {len(records)}")
    return {
        "schema_version": 1,
        "publisher": "National Infrastructure and Service Transformation Authority",
        "source_url": SOURCE_PAGE,
        "download_url": URL,
        "as_of_date": "2025-03-31",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "columns": fields,
        "record_count": len(records),
        "records": records,
        "notice": "Unmapped official source columns; figures retain their original units and definitions.",
    }

def find_field(row, patterns):
    for pattern in patterns:
        for key, value in row.items():
            if re.search(pattern, key, re.I) and str(value or "").strip():
                return str(value).strip()
    return ""

def make_catalogue(data):
    """Publish all identifiable project rows, without guessing financial units."""
    projects = []
    seen = set()
    for index, row in enumerate(data["records"]):
        name = find_field(row, [r"^project\\s*(name|title)$", r"^name\\s*of\\s*project$", r"project.*name"])
        if not name:
            continue
        department = find_field(row, [r"^department$", r"department\\s*name", r"organisation", r"organization"])
        description = find_field(row, [r"^project\\s*description$", r"^description$", r"project\\s*summary", r"project\\s*purpose", r"project\\s*objective"])
        sector = find_field(row, [r"^sector$", r"^category$", r"project\\s*type"])
        identifier = hashlib.sha256((name + "\\0" + department).encode("utf-8")).hexdigest()[:20]
        if identifier in seen:
            continue
        seen.add(identifier)
        projects.append({
            "id": "nista-" + identifier,
            "name": name,
            "description": description or " · ".join(x for x in (sector, department) if x) or "UK government major project",
            "department": department,
            "sector": sector,
            "nation": "United Kingdom",
            "status": "",
            "source_url": SOURCE_PAGE,
            "source_title": "NISTA Annual Report 2024-25",
            "source_as_of": "2025-03-31",
            "original_budget_gbp": None,
            "current_forecast_gbp": None,
            "actual_spend_gbp": None,
            "original_completion": None,
            "forecast_completion": None,
            "actual_completion": None,
            "notes": "Original source columns retained in NISTA source-records view. Financial values are omitted until column units and definitions are verified."
        })
    if len(projects) < 20:
        raise ValueError(f"Only {len(projects)} named projects found; check NISTA CSV headings")
    projects.sort(key=lambda item: item["name"].casefold())
    return {"schema_version": 1, "generated_at": data["retrieved_at"],
            "project_count": len(projects), "projects": projects}

def main():
    request = urllib.request.Request(URL, headers={"User-Agent": "UKPublicMoneyMonitor/0.4", "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(15_000_001)
    data = build(raw)
    catalogue = make_catalogue(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    project_tmp = PROJECTS_OUT.with_suffix(".tmp")
    project_tmp.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(project_tmp, PROJECTS_OUT)
    print(f"Published {catalogue['project_count']} searchable project names")
    print(f"Published {data['record_count']} official CSV rows; sha256={data['sha256']}")

if __name__ == "__main__":
    main()
