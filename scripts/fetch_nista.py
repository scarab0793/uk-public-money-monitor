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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://assets.publishing.service.gov.uk/media/6895fbb63080e72710b2e2ef/nista_annual_report_data_2425.csv"
SOURCE_PAGE = "https://www.gov.uk/government/publications/nista-annual-report-2024-2025"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nista-raw-projects.json"

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

def main():
    request = urllib.request.Request(URL, headers={"User-Agent": "UKPublicMoneyMonitor/0.4", "Accept": "text/csv,*/*"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(15_000_001)
    data = build(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"Published {data['record_count']} official CSV rows; sha256={data['sha256']}")

if __name__ == "__main__":
    main()
