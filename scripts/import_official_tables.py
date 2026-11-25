"""Import official HMRC and HM Treasury statistics tables published on GOV.UK.

  hmrc-receipts  HMRC tax receipts and NICs for the UK (cash basis), monthly and
                 by financial year, every published tax and duty column.
  pss-tes        HM Treasury Public Spending Statistics: total expenditure on
                 services (TES) by function, Tables 9/9a/9b (nominal, real terms,
                 share of GDP) - outturn and plans kept apart.

Publications are discovered through the GOV.UK Content and Search APIs, so new
monthly/quarterly releases are picked up without code changes.  Every output
records the publication page, the attachment URL and the release timestamp.  A
source that fails to download or validate keeps its previous output; the failure
is written to data/official-tables-report.json.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd
import requests

GOVUK = "https://www.gov.uk"
UA = {"User-Agent": "uk-public-money-monitor/1.0 (+https://github.com/scarab0793/uk-public-money-monitor)"}
OUT = {"hmrc-receipts": Path("data/hmrc/receipts.json"), "pss-tes": Path("data/treasury/pss-expenditure-on-services.json")}
REPORT = Path("data/official-tables-report.json")


def content(path):
    r = requests.get(GOVUK + "/api/content/" + path.strip("/"), headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()


def attachment(doc, pattern):
    for a in doc.get("details", {}).get("attachments") or []:
        url = a.get("url") or ""
        if re.search(pattern, (a.get("title") or "") + " " + url, re.I) and url.lower().endswith((".ods", ".xlsx")):
            return a
    raise RuntimeError(f"No attachment matching {pattern!r} on {doc.get('base_path')}")


def read_book(url):
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    engine = "odf" if url.lower().endswith(".ods") else "openpyxl"
    return pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None, engine=engine)


def cell_number(v):
    """Numbers stay numbers; '[x]', '..', '-' and blanks become None (not zero)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


MONTH_RE = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$")
FY_RE = re.compile(r"^(\d{4})\s*(?:to|-|–)\s*(\d{2,4})$")


def norm_fy(label):
    m = FY_RE.match(str(label).strip())
    if not m:
        return None
    start = int(m.group(1))
    return f"{start}-{str(start + 1)[2:]}"


def norm_month(label):
    if isinstance(label, (dt.datetime, pd.Timestamp)):
        return label.strftime("%Y-%m")
    m = MONTH_RE.match(str(label).strip())
    if not m:
        return None
    return dt.datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %Y").strftime("%Y-%m")


def parse_wide_table(df, period_parser, header_prefix):
    """HMRC layout: a header row whose first cell starts with header_prefix, then one row per period."""
    hdr = None
    for i in range(min(len(df), 40)):
        if str(df.iat[i, 0]).strip().startswith(header_prefix):
            hdr = i
            break
    if hdr is None:
        raise RuntimeError(f"Header row {header_prefix!r} not found")
    columns = [str(c).strip() for c in df.iloc[hdr, 1:].tolist()]
    series = {c: [] for c in columns if c and c != "nan"}
    for i in range(hdr + 1, len(df)):
        period = period_parser(df.iat[i, 0])
        if not period:
            continue
        for j, col in enumerate(columns, start=1):
            if col in series:
                series[col].append([period, cell_number(df.iat[i, j])])
    return series


def notes_text(df):
    return [str(v).strip() for v in df.iloc[:, 0].tolist() if isinstance(v, str) and v.strip()][:80]


def import_hmrc_receipts():
    page = "government/statistics/hmrc-tax-and-nics-receipts-for-the-uk"
    doc = content(page)
    att = attachment(doc, r"statistics table|NS_Table")
    book = read_book(att["url"])
    monthly = parse_wide_table(book["Receipts_Monthly"], norm_month, "Table 1")
    annual = parse_wide_table(book["Receipts_Annually"], norm_fy, "Table 2")
    total = "Total HMRC Receipts"
    if total not in monthly or len(monthly[total]) < 60 or total not in annual or len(annual[total]) < 10:
        raise RuntimeError("Receipts tables failed validation")
    latest = max(p for p, v in monthly[total] if v is not None)
    taxes = []
    for name in annual:
        a = [[p, v] for p, v in annual[name]]
        m = monthly.get(name, [])
        taxes.append(dict(name=name, aggregate=name.lower().startswith("total"), annual=a, monthly=m,
                          first_month=next((p for p, v in m if v is not None), None)))
    return dict(
        dataset="HMRC tax receipts and National Insurance contributions for the UK",
        publisher="HM Revenue & Customs",
        page=GOVUK + "/" + page, attachment=att["url"], release_updated_at=doc.get("public_updated_at"),
        unit="GBP million", accounting_basis="cash receipts", price_basis="nominal",
        latest_month=latest,
        caveats=["Cash receipts are when money reaches HMRC, which differs from accrued revenue in HMRC's annual accounts.",
                 "Columns include totals and their components (for example Income Tax and PAYE Income Tax); do not add columns together.",
                 "[x] in the source (not available or not applicable) is stored as null, not zero. Negative values are repayments and are kept.",
                 "Recent months are provisional and are revised in later releases."],
        notes=notes_text(book.get("Table_Notes", pd.DataFrame([[""]]))),
        taxes=taxes,
    )


def find_latest_pss():
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": "Public Spending Statistics release", "filter_organisations": "hm-treasury", "order": "-public_timestamp",
        "count": 20, "fields": "title,link,public_timestamp"}).json()
    for r in q.get("results", []):
        if re.match(r"public spending statistics release", r.get("title", ""), re.I) and r.get("link", "").startswith("/government/statistics/"):
            yield r["link"]


def parse_tes(df):
    title = str(df.iat[0, 0]).strip()
    year_row = None
    for i in range(min(len(df), 15)):
        cells = [str(v) for v in df.iloc[i, 1:].tolist()]
        if sum(bool(re.fullmatch(r"\d{4}-\d{2}", c.strip())) for c in cells) >= 5:
            year_row = i
            break
    if year_row is None:
        raise RuntimeError("Year row not found in " + title[:40])
    years = [str(v).strip() for v in df.iloc[year_row, 1:].tolist()]
    kinds = [str(v).strip().lower() for v in df.iloc[year_row + 1, 1:].tolist()]
    rows = []
    for i in range(year_row + 2, len(df)):
        label = df.iat[i, 0]
        if not isinstance(label, str) or not label.strip():
            continue
        label = label.strip()
        values = []
        for y, k, v in zip(years, kinds, df.iloc[i, 1:].tolist()):
            if re.fullmatch(r"\d{4}-\d{2}", y):
                values.append([y, k if k in ("outturn", "plans", "plan", "forecast") else None, cell_number(v)])
        if not any(v[2] is not None for v in values):
            continue  # footnote line
        level = "component" if label.lower().startswith("of which") else ("total" if label.lower().startswith("total") or "accounting adjustments" in label.lower() else "function")
        rows.append(dict(label=label, level=level, values=values))
    return dict(title=title, rows=rows)


def import_pss():
    errors = []
    for link in find_latest_pss():
        try:
            doc = content(link)
            att = attachment(doc, r"expenditure on services|TES")
            book = read_book(att["url"])
            tables = {}
            for name in ("Table_9", "Table_9a", "Table_9b"):
                if name in book:
                    tables[name] = parse_tes(book[name])
            if "Table_9" not in tables or len([r for r in tables["Table_9"]["rows"] if r["level"] == "function"]) < 8:
                raise RuntimeError("Table 9 failed validation")
            return dict(
                dataset="Public Spending Statistics: total expenditure on services by function",
                publisher="HM Treasury", page=GOVUK + link, attachment=att["url"], release_updated_at=doc.get("public_updated_at"),
                unit="GBP billion (Table 9b: per cent of GDP)",
                caveats=["Total expenditure on services (TES) is close to, but not the same as, Total Managed Expenditure (TME).",
                         "'of which' rows are components of the function above and must not be added to it.",
                         "Plans are budgets and forecasts, not outturn spending.",
                         "Table 9a is in real terms at the base year stated in its title; Table 9 is nominal."],
                tables=tables)
        except Exception as exc:
            errors.append(f"{link}: {exc}")
    raise RuntimeError("; ".join(errors) or "No Public Spending Statistics release found")


IMPORTERS = {"hmrc-receipts": import_hmrc_receipts, "pss-tes": import_pss}


def main(names):
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok = 0
    for name in names or IMPORTERS:
        try:
            payload = IMPORTERS[name]()
            payload["retrieved_at"] = now
            path = OUT[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            old = json.loads(path.read_text()) if path.exists() else None
            if old and {k: v for k, v in old.items() if k != "retrieved_at"} == {k: v for k, v in payload.items() if k != "retrieved_at"}:
                status = "unchanged"
            else:
                path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                status = "updated"
            report[name] = dict(status=status, checked_at=now, attachment=payload.get("attachment"), release_updated_at=payload.get("release_updated_at"))
            ok += 1
        except Exception as exc:
            prev = report.get(name, {})
            report[name] = dict(prev, status="failed_kept_previous", checked_at=now, error=str(exc)[:500])
        print(name, report[name]["status"], report[name].get("error", ""))
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
