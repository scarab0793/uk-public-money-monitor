"""Verify the 2025-26 major projects records (transcribed from the ProjectLens mirror)
against NISTA's official CSV on GOV.UK, and publish the official rows verbatim.

Outputs
  data/nista-2025-26-official.json            official CSV rows, unchanged
  data/audits/gmpp-2025-26-verification.json  field-by-field agreement report

Columns are matched automatically: for each field of the transcribed file, the
official column with the highest value agreement across matched projects is
chosen.  Money fields in the transcription are in GBP, the official file in GBP
millions, so numeric comparison tries both scales.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import requests

PAGE = "https://www.gov.uk/government/publications/nista-major-projects-annual-report-2025-26"
API = "https://www.gov.uk/api/content/government/publications/nista-major-projects-annual-report-2025-26"
TRANSCRIBED = Path("data/gmpp-2025-26-full-records.json")
OFFICIAL_OUT = Path("data/nista-2025-26-official.json")
AUDIT_OUT = Path("data/audits/gmpp-2025-26-verification.json")


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().casefold()


def num(v):
    s = str(v or "").replace(",", "").replace("£", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def same(a, b):
    if norm(a) == norm(b):
        return True
    # A blank transcribed value for an official non-numeric entry (exemption, range, "not yet costed")
    # is the intended treatment: the text is kept in the official rows and never shown as a number.
    if norm(a) in ("", "none") and num(b) is None:
        return True
    x, y = num(a), num(b)
    if x is None or y is None:
        return False
    for scale in (1, 1e6, 1e-6):
        if abs(x - y * scale) <= max(0.5, abs(x) * 0.0005):
            return True
    return False


def main():
    doc = requests.get(API, timeout=60).json()
    url = next(a["url"] for a in doc["details"]["attachments"] if (a.get("url") or "").lower().endswith(".csv"))
    raw = requests.get(url, timeout=120).content
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows if any((v or "").strip() for v in r.values())]
    cols = list(rows[0].keys())
    OFFICIAL_OUT.write_text(json.dumps(dict(
        schema_version=1, publisher="National Infrastructure and Service Transformation Authority", source_url=PAGE, download_url=url,
        release_updated_at=doc.get("public_updated_at"), retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        sha256=hashlib.sha256(raw).hexdigest(), columns=cols, record_count=len(rows), records=rows,
        notice="Official NISTA CSV rows, unchanged. Financial columns are in the units stated in their headings."), ensure_ascii=False, indent=1), encoding="utf-8")

    transcribed = json.loads(TRANSCRIBED.read_text())["records"]
    name_col = max(cols, key=lambda c: sum(norm(r.get(c)) in {norm(t["project_name"]) for t in transcribed} for r in rows))
    off_by_name = {}
    for r in rows:
        off_by_name.setdefault(norm(r[name_col]), []).append(r)
    pairs, unmatched = [], []
    for t in transcribed:
        cands = off_by_name.get(norm(t["project_name"]), [])
        if len(cands) > 1 and t.get("major_projects_id"):
            cands = [c for c in cands if any(norm(v) == norm(t["major_projects_id"]) for v in c.values())] or cands
        if len(cands) == 1:
            pairs.append((t, cands[0]))
        else:
            unmatched.append(dict(project=t["project_name"], candidates=len(cands)))
    fields = {}
    for f in transcribed[0]:
        best = None
        for c in cols:
            agree = sum(same(t.get(f), o.get(c)) for t, o in pairs)
            if best is None or agree > best[1]:
                best = (c, agree)
        diffs = [dict(project=t["project_name"], transcribed=t.get(f), official=o.get(best[0])) for t, o in pairs if not same(t.get(f), o.get(best[0]))]
        rate = best[1] / len(pairs) if pairs else 0
        fields[f] = dict(official_column=best[0], agreement=round(rate, 4), differences=len(diffs), examples=diffs[:10],
                         status="verified" if rate == 1 else ("partially_verified" if rate >= 0.95 else "disputed"))
    official_names = {norm(t["project_name"]) for t in transcribed}
    report = dict(
        checked_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), official_source=url, page=PAGE,
        transcribed_file=str(TRANSCRIBED), transcribed_records=len(transcribed), official_records=len(rows),
        matched=len(pairs), unmatched_transcribed=unmatched,
        official_not_in_transcription=[r[name_col] for r in rows if norm(r[name_col]) not in official_names][:50],
        fields=fields,
        overall_status="verified" if pairs and len(pairs) == len(transcribed) == len(rows) and all(v["status"] == "verified" for v in fields.values())
        else "partially_verified")
    AUDIT_OUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "fields"}, indent=1)[:3000])
    for f, v in fields.items():
        print(f"{f:45s} -> {v['official_column'][:45]:45s} {v['agreement']:.3f} {v['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
