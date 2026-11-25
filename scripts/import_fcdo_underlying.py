"""Import the official FCDO 'Statistics on International Development: final UK ODA spend' underlying data.

Each annual release (published in the autumn after the year ends) contains the full
2017-to-latest series, so the normaliser uses only the newest vintage; older vintages are
kept as an archive.  Years are discovered automatically: every year from 2024 to the
current one is tried, a release that is not yet published is skipped, and a year whose
download fails keeps the files from the previous successful import.
"""
import datetime
import json
import pathlib
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

out = pathlib.Path("data/fcdo")
out.mkdir(parents=True, exist_ok=True)
manifest_path = out / "manifest.json"
previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
manifest, report = [], []
for year in range(2024, datetime.date.today().year + 1):
    page = f"https://www.gov.uk/government/statistics/statistics-on-international-development-final-uk-oda-spend-{year}"
    try:
        r = requests.get(page, timeout=90)
        if r.status_code == 404:
            report.append(dict(year=year, status="not yet published", page=page))
            continue
        r.raise_for_status()
        links = BeautifulSoup(r.text, "html.parser").find_all("a", href=True)
        matches = [urljoin(page, a["href"]) for a in links if "data underlying" in a.get_text(" ", strip=True).lower() and ".ods" in a["href"].lower()]
        if not matches:
            raise RuntimeError(f"No underlying ODS for {year}")
        url = matches[0]
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        path = out / f"oda-{year}.ods"
        path.write_bytes(response.content)
        book = pd.ExcelFile(path, engine="odf")
        entries = []
        for i, sheet in enumerate(book.sheet_names):
            df = book.parse(sheet, header=None)
            dest = out / f"oda-{year}-sheet-{i}.csv"
            df.to_csv(dest, index=False, header=False)
            entries.append(dict(year=year, sheet=sheet, rows=len(df), columns=len(df.columns), file=str(dest), source=url, page=page))
        path.unlink()
        if not any(e["sheet"] == "Data" and e["rows"] > 1000 for e in entries):
            raise RuntimeError(f"{year}: no Data sheet with rows")
        manifest.extend(entries)
        report.append(dict(year=year, status="imported", source=url))
    except Exception as exc:  # keep the last good import for this year
        kept = [e for e in previous if e["year"] == year]
        manifest.extend(kept)
        report.append(dict(year=year, status="failed", error=str(exc)[:300], kept_previous=len(kept)))
if not any(e["sheet"] == "Data" for e in manifest):
    raise SystemExit("No FCDO data available")
manifest_path.write_text(json.dumps(manifest, indent=2))
(out / "import-report.json").write_text(json.dumps(dict(checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), years=report), indent=2))
print(json.dumps(report, indent=1))
