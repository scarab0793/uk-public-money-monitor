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
OUT = {"hmrc-receipts": Path("data/hmrc/receipts.json"), "pss-tes": Path("data/treasury/pss-expenditure-on-services.json"),
       "cra": Path("data/treasury/country-regional-analysis.json"), "council-tax": Path("data/local-government/council-tax-england.json")}
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
        if str(df.iat[i, 0]).strip().startswith(header_prefix) and df.iloc[i, 1:].notna().sum() >= 3:
            hdr = i
            break
    if hdr is None:
        raise RuntimeError(f"Header row {header_prefix!r} not found")
    columns = [re.sub(r"\s+", " ", re.sub(r"\s*\[(?:note|Note)[^\]]*\]", "", str(c))).strip() for c in df.iloc[hdr, 1:].tolist()]
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
    total = next((c for c in annual if c.lower().startswith("total hmrc receipts")), None)
    if not total or total not in monthly or len(monthly[total]) < 60 or total not in annual or len(annual[total]) < 10:
        raise RuntimeError("Receipts tables failed validation: columns=%s monthly=%d annual=%d" % (list(annual)[:6], len(monthly.get(total) or []), len(annual.get(total) or [])))
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
        low = label.lower()
        if low.startswith("of which"):
            level = "component"
        elif low.startswith(("total", "public sector expenditure on services")):
            level = "total"
        elif low.startswith("accounting adjustments"):
            level = "adjustment"
        else:
            level = "function"
        name = re.sub(r"\s*\(\d+\)(?:,\s*\(\d+\))*", "", label)
        name = re.sub(r"^(?:\d+\.\s*|of which:\s*)", "", name).strip()
        rows.append(dict(label=label, name=name[:1].upper() + name[1:], level=level, values=values))
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


ENGLISH_REGIONS = {"north east", "north west", "yorkshire and the humber", "east midlands", "west midlands", "east", "london", "south east", "south west"}
NATIONS = {"england", "scotland", "wales", "northern ireland"}


def area_level(label):
    low = re.sub(r"\s*\(\d+\)", "", label).strip().lower()
    if low in ENGLISH_REGIONS:
        return "english_region"
    if low in NATIONS:
        return "nation"
    if low.startswith("total ") and low[6:] in NATIONS:
        return "nation"
    if "identifiable" in low or low.startswith(("uk", "united kingdom", "total")) or "outside" in low or "non-identifiable" in low:
        return "total_or_other"
    return "other"


def parse_cra_table(df):
    """CRA layout: title row, unit row(s), a row of 'YYYY-YY\noutturn' headers in one or two blocks, then one row per area."""
    title = str(df.iat[0, 0]).strip()
    hdr = None
    for i in range(min(len(df), 12)):
        if sum(bool(re.match(r"\d{4}-\d{2}", str(v).strip())) for v in df.iloc[i, 1:].tolist()) >= 3:
            hdr = i
            break
    if hdr is None:
        raise RuntimeError("No year header in " + title[:40])
    heads = [str(v).strip() for v in df.iloc[hdr, 1:].tolist()]
    units = []
    for j in range(1, df.shape[1]):
        u = next((str(df.iat[i, j]).strip() for i in range(hdr - 1, 0, -1) if isinstance(df.iat[i, j], str) and not df.iat[i, j].startswith("Accredited")), None)
        units.append(u)
    blocks, current, seen = [], None, set()
    for j, h in enumerate(heads):
        m = re.match(r"(\d{4}-\d{2})\s*(\w*)", h)
        if not m:
            continue
        if current is None or m.group(1) in seen:
            current = dict(unit=units[j] or (blocks[-1]["unit"] if blocks else None), cols=[])
            blocks.append(current)
            seen = set()
        if units[j] and not current["cols"]:
            current["unit"] = units[j]
        seen.add(m.group(1))
        current["cols"].append((j + 1, m.group(1), m.group(2) or None))
    # a unit label usually sits above the last column of its block
    for b in blocks:
        last = b["cols"][-1][0] - 1
        if units[last]:
            b["unit"] = units[last]
    rows = []
    for i in range(hdr + 1, len(df)):
        label = df.iat[i, 0]
        if not isinstance(label, str) or not label.strip():
            continue
        vals = [[[y, k, cell_number(df.iat[i, c])] for c, y, k in b["cols"]] for b in blocks]
        if not any(v[2] is not None for blk in vals for v in blk):
            continue
        label = label.strip()
        rows.append(dict(area=re.sub(r"\s*\(\d+\)", "", label), label=label, level=area_level(label), blocks=vals))
    return dict(title=title, units=[b["unit"] for b in blocks], rows=rows)


def find_latest(query, title_re):
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": query, "filter_organisations": "hm-treasury", "order": "-public_timestamp", "count": 20, "fields": "title,link"}).json()
    for r in q.get("results", []):
        if re.match(title_re, r.get("title", ""), re.I) and r.get("link", "").startswith("/government/statistics/"):
            yield r["link"]


def import_cra():
    errors = []
    for link in find_latest("Country and regional analysis", r"country and regional analysis:? \d{4}$"):
        try:
            doc = content(link)
            att = attachment(doc, r"A tables|Chapter_A")
            book = read_book(att["url"])
            tables = {k: parse_cra_table(book[k]) for k in ("A.1a", "A.1b", "A.2a", "A.2b") if k in book}
            if "A.1b" not in tables or len([r for r in tables["A.1b"]["rows"] if r["level"] == "english_region"]) != 9:
                raise RuntimeError("Table A.1b failed validation")
            return dict(
                dataset="Country and Regional Analysis: identifiable public spending by country and region",
                publisher="HM Treasury", page=GOVUK + link, attachment=att["url"], release_updated_at=doc.get("public_updated_at"),
                caveats=["Identifiable expenditure only: spending that can be attributed to a region (for example defence and debt interest are largely non-identifiable).",
                         "English regions add up to England, and the four nations to the UK identifiable total; do not add regional and national rows together.",
                         "Per head figures use mid-year population estimates. Real-terms tables use the price base stated in their titles.",
                         "Spending is attributed by where the benefit is received ('who benefits'), not where the money is paid out."],
                tables=tables)
        except Exception as exc:
            errors.append(f"{link}: {exc}")
    raise RuntimeError("; ".join(errors) or "No Country and Regional Analysis release found")


def parse_header_table(df, key="Authority"):
    """Generic MHCLG layout: title in row 0, a header row containing `key`, data rows until the end."""
    title = str(df.iat[0, 0]).strip()
    hdr = next(i for i in range(min(len(df), 15)) if any(str(v).strip() == key for v in df.iloc[i].tolist()))
    heads = [re.sub(r"\s+", " ", str(v)).strip() if str(v) != "nan" else None for v in df.iloc[hdr].tolist()]
    rows = []
    for i in range(hdr + 1, len(df)):
        vals = df.iloc[i].tolist()
        if all(str(v) == "nan" for v in vals):
            continue
        rec = {}
        for h, v in zip(heads, vals):
            if not h:
                continue
            n = cell_number(v)
            rec[h] = n if n is not None and h not in ("E-code", "E Code", "ONS Code") else (None if str(v) in ("nan", "[x]", "[z]") else str(v).strip())
        if rec.get(key):
            rows.append(rec)
    return dict(title=title, columns=[h for h in heads if h], rows=rows)


def import_council_tax():
    org = "ministry-of-housing-communities-local-government"
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": "Council Tax levels set by local authorities in England", "filter_organisations": org, "order": "-public_timestamp", "count": 20, "fields": "title,link"}).json()
    errors = []
    for r in q.get("results", []):
        if not re.match(r"council tax levels set by local authorities in england \d{4} to \d{4}$", r.get("title", ""), re.I):
            continue
        try:
            doc = content(r["link"])
            att = attachment(doc, r"Tables 1 to 9|Tables_1-9")
            book = read_book(att["url"])
            t9 = parse_header_table(book["Table_9"])
            t8 = parse_header_table(book["Table_8a"]) if "Table_8a" in book else None
            bands = [c for c in t9["columns"] if c.startswith("Band")]
            if len(t9["rows"]) < 250 or len(bands) != 8:
                raise RuntimeError(f"Table 9 failed validation ({len(t9['rows'])} rows, bands {bands})")
            year = re.search(r"(\d{4}) to (\d{4})$", r["title"])
            return dict(
                dataset=r["title"], publisher="Ministry of Housing, Communities and Local Government", page=GOVUK + r["link"],
                attachment=att["url"], release_updated_at=doc.get("public_updated_at"),
                financial_year=f"{year.group(1)}-{year.group(2)[2:]}", unit="GBP per year",
                caveats=["Area council tax is the total bill for a dwelling occupied by two adults, including county, police, fire and combined authority precepts but excluding parish precepts.",
                         "Bills are reduced by discounts, exemptions and Council Tax Support; most dwellings are in Bands A to C.",
                         "England only. Scotland, Wales and Northern Ireland (domestic rates) have separate systems."],
                area_bills=t9, authority_band_d=t8)
        except Exception as exc:
            errors.append(f"{r['link']}: {exc}")
    raise RuntimeError("; ".join(errors) or "No Council Tax levels release found")


IMPORTERS = {"hmrc-receipts": import_hmrc_receipts, "pss-tes": import_pss, "cra": import_cra, "council-tax": import_council_tax}


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
