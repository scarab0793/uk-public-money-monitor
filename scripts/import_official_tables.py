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
       "cra": Path("data/treasury/country-regional-analysis.json"), "council-tax": Path("data/local-government/council-tax-england.json"),
       "dwp-benefits": Path("data/welfare/benefit-expenditure-caseloads.json"),
       "la-outturn": Path("data/local-government/revenue-outturn-england.json"),
       "nhs-trust-accounts": Path("data/nhs/trust-accounts.json"),
       "grants": Path("data/grants/government-grants.json"),
       "wales-la-outturn": Path("data/local-government/revenue-outturn-wales.json"),
       "wales-nhs-programme": Path("data/nhs/wales-programme-budgets.json")}
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


def read_book(url, engine=None):
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    engine = engine or ("odf" if url.lower().endswith(".ods") else "openpyxl")
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
    """Newest Public Spending Statistics releases first.  The organisation filter on the GOV.UK search API
    sometimes returns nothing, so an unfiltered query is tried as well and the hits are sorted here."""
    hits = {}
    for extra in ({"filter_organisations": "hm-treasury", "order": "-public_timestamp"}, {}):
        try:
            q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
                "q": "Public Spending Statistics release", "count": 40, "fields": "title,link,public_timestamp", **extra}).json()
        except (requests.RequestException, ValueError):
            continue
        for r in q.get("results", []):
            if re.match(r"public spending statistics release", r.get("title", ""), re.I) and r.get("link", "").startswith("/government/statistics/"):
                hits[r["link"]] = r.get("public_timestamp", "")
        if hits:
            break
    yield from sorted(hits, key=hits.get, reverse=True)[:6]


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


def parse_cra_by_function(df):
    """Table A.15 layout: function names across one header row; a year label row, then one row per area."""
    title = str(df.iat[0, 0]).strip()
    hdr = next(i for i in range(min(len(df), 10)) if sum(isinstance(v, str) and re.match(r"\s*(\d+\.|of which)", v) is not None for v in df.iloc[i].tolist()) >= 5)
    funcs = {}
    for j, v in enumerate(df.iloc[hdr].tolist()):
        if isinstance(v, str) and v.strip() and not v.strip().lower().startswith("total"):
            name = v.strip()
            funcs[j] = dict(label=name, name=re.sub(r"^(?:\d+\.\s*|of which:\s*)", "", name).strip(), level="component" if name.lower().startswith("of which") else "function")
    years, year = {}, None
    for i in range(hdr + 1, len(df)):
        lab = df.iat[i, 0]
        if not isinstance(lab, str) or not lab.strip():
            continue
        lab = lab.strip()
        if re.fullmatch(r"\d{4}-\d{2}", lab):
            year = lab
            continue
        if year is None:
            continue
        vals = {funcs[j]["name"]: cell_number(df.iat[i, j]) for j in funcs}
        if any(v is not None for v in vals.values()):
            years.setdefault(year, []).append(dict(area=re.sub(r"\s*\(\d+\)", "", lab), level=area_level(lab), values=vals))
    return dict(title=title, functions=list(funcs.values()), years=years)


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
            if "A.15" in book:
                tables["A.15"] = parse_cra_by_function(book["A.15"])
                if not any(len(v) >= 13 for v in tables["A.15"]["years"].values()):
                    raise RuntimeError("Table A.15 failed validation")
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
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": "Council Tax levels set by local authorities in England", "count": 40, "fields": "title,link"}).json()
    hits = [r for r in q.get("results", []) if re.match(r"council tax levels set by local authorities in england \d{4} to \d{4}$", r.get("title", ""), re.I)
            and r.get("link", "").startswith("/government/statistics/")]
    hits.sort(key=lambda r: r["title"][-12:], reverse=True)  # newest financial year first
    errors = []
    for r in hits:
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


YEAR_COL_RE = re.compile(r"^(\d{4})/(\d{2})$")


def parse_dwp_table(df):
    """DWP layout: row with the table title and 'YYYY/YY' year headers, the next row with the unit and
    Outturn/Forecast flags, then one row per line item (label in column 1, optional marker in column 2).
    Rows without any number are section headings for the rows that follow."""
    hdr = next(i for i in range(min(len(df), 10)) if sum(bool(YEAR_COL_RE.match(str(v).strip())) for v in df.iloc[i]) >= 3)
    cols = [(j, str(v).strip()) for j, v in enumerate(df.iloc[hdr]) if YEAR_COL_RE.match(str(v).strip())]
    years = [f"{y[:4]}-{y[5:]}" for _, y in cols]
    flags = [str(df.iat[hdr + 1, j]).strip().lower() for j, _ in cols]
    title = " ".join(str(v).strip() for v in df.iloc[hdr, :cols[0][0]] if isinstance(v, str) and not re.match(r"^(autumn|spring) forecast$", v.strip(), re.I)).strip().rstrip(",")
    unit = " ".join(str(v).strip() for v in df.iloc[hdr + 1, 1:cols[0][0]] if isinstance(v, str) and v.strip() != "Benefit type")
    rows, section = [], None
    for i in range(hdr + 2, len(df)):
        label = df.iat[i, 1]
        if not isinstance(label, str) or not label.strip():
            continue
        label = re.sub(r"\s+", " ", label).strip().rstrip(",")
        vals = [cell_number(df.iat[i, j]) for j, _ in cols]
        if all(v is None for v in vals):
            if re.match(r"^(notes?|source)", label, re.I):
                break
            section = label
            continue
        marker = df.iat[i, 2] if cols[0][0] > 2 and isinstance(df.iat[i, 2], str) else None
        rows.append(dict(name=label, marker=marker, section=section, values=vals))
    return dict(title=title, unit=unit, years=years, forecast=[f.startswith("forecast") for f in flags], rows=rows)


def dwp_total_check(t):
    """The benefit lines above 'Total benefit expenditure' must add up to it in every year."""
    rows = t["rows"]
    cut = next(i for i, r in enumerate(rows) if r["name"].lower().startswith("total benefit expenditure"))
    items = [r for r in rows[:cut] if not r["name"].lower().startswith("of which")]
    bad = []
    for i, y in enumerate(t["years"]):
        total = rows[cut]["values"][i]
        s = sum(r["values"][i] or 0 for r in items)
        if total is None or abs(s - total) > max(1, abs(total) * 0.001):
            bad.append(y)
    return dict(check="benefit lines sum to the published total", years_checked=len(t["years"]), years_mismatched=bad)


def import_dwp_benefits():
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": "Benefit expenditure and caseload tables", "count": 40, "fields": "title,link"}).json()
    hits = [r for r in q.get("results", []) if re.match(r"benefit expenditure and caseload tables \d{4}$", r.get("title", ""), re.I)
            and r.get("link", "").startswith("/government/publications/")]
    hits.sort(key=lambda r: r["title"][-4:], reverse=True)
    errors = []
    for r in hits[:2]:
        try:
            doc = content(r["link"])
            atts = [a for a in doc["details"].get("attachments") or [] if (a.get("url") or "").lower().endswith(".ods")
                    and re.search(r"outturn-and-forecast|expenditure-and-caseloads-tables", a["url"], re.I)]
            if not atts:
                raise RuntimeError("no outturn and forecast tables attachment")
            # within a year's collection the autumn forecast supersedes the spring one
            att = max(atts, key=lambda a: ("autumn" in (a.get("title", "") + a["url"]).lower(), atts.index(a)))
            book = read_book(att["url"])
            tables = {k: parse_dwp_table(book[k]) for k in ("Table_1a", "Table_1b", "Table_1c")}
            names = {x["name"] for x in tables["Table_1a"]["rows"]}
            if len(tables["Table_1a"]["rows"]) < 30 or not any(n.startswith("State Pension") for n in names) or "nominal" not in tables["Table_1a"]["unit"]:
                raise RuntimeError(f"Table 1a failed validation ({len(tables['Table_1a']['rows'])} rows, unit {tables['Table_1a']['unit']!r})")
            checks = {k: dwp_total_check(tables[k]) for k in ("Table_1a", "Table_1b")}
            for k, c in checks.items():
                if c["years_mismatched"]:
                    raise RuntimeError(f"{k}: benefit lines do not add up to the published total in {c['years_mismatched']}")
            notes = [" ".join(str(v).strip() for v in row if isinstance(v, str) and v.strip()) for row in book["Notes"].itertuples(index=False)] if "Notes" in book else []
            notes = [n for n in notes if n][:120]
            return dict(
                dataset=f"{r['title']}: {att.get('title', '').strip()}", publisher="Department for Work and Pensions", page=GOVUK + r["link"],
                attachment=att["url"], release_updated_at=doc.get("public_updated_at"), tables=tables, checks=checks, notes=notes,
                caveats=["Great Britain DWP benefit expenditure; Northern Ireland social security is paid by the NI Executive and is not included in these tables.",
                         "Benefits devolved to Scotland are counted by DWP only until the Scottish Government took them over.",
                         "Years marked as forecast are DWP projections at the time of the fiscal event, not spending.",
                         "Real-terms figures are in the price base stated in the table heading; never add them to nominal figures."])
        except Exception as exc:
            errors.append(f"{r['link']}: {exc}")
    raise RuntimeError("; ".join(errors) or "No benefit expenditure tables found")


RSX_MEASURES = {"C3": "total_expenditure", "C6": "total_income", "C7": "net_current_expenditure"}


def parse_rsx(df):
    """MHCLG RSX 'data by LA' sheet: a header row starting with 'E-code', columns '<service> - <measure> (Cn ...)',
    then one row per authority.  Values are £ thousand; blanks and symbols stay None."""
    hdr = next(i for i in range(min(len(df), 30)) if str(df.iat[i, 0]).strip().lower() == "e-code")
    head = [re.sub(r"\s+", " ", str(v)).strip() for v in df.iloc[hdr]]
    idx = {h.lower(): j for j, h in enumerate(head)}
    cols, services = {}, []
    for j, h in enumerate(head):
        m = re.match(r"^(.+?) - .*\((C\d+[a-z]?)\b", h)
        if m and m.group(2) in RSX_MEASURES:
            svc = m.group(1).strip()
            if svc not in services:
                services.append(svc)
            cols[(svc, RSX_MEASURES[m.group(2)])] = j
    measures = list(RSX_MEASURES.values())
    rows, problems = [], 0
    for i in range(hdr + 1, len(df)):
        code = str(df.iat[i, 0]).strip()
        if not re.match(r"^E\d{4}$", code):
            continue
        vals = {}
        for svc in services:
            v = [cell_number(df.iat[i, cols[(svc, m)]]) if (svc, m) in cols else None for m in measures]
            if None not in v and abs(v[0] - v[1] - v[2]) > 2:
                problems += 1
            vals[svc] = v
        get = lambda name: (str(df.iat[i, idx[name]]).strip() if name in idx and str(df.iat[i, idx[name]]) != "nan" else None)
        rows.append(dict(ecode=code, ons=get("ons code"), name=get("local authority"), cls=get("class"), notes=get("notes"), values=vals))
    return dict(unit="£ thousand", services=services, measures=measures, authorities=rows, identity_failures=problems)


def import_la_outturn():
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={
        "q": "Local authority revenue expenditure and financing England individual local authority data outturn", "count": 40, "fields": "title,link"}).json()
    hits = {}
    for r in q.get("results", []):
        m = re.search(r"(\d{4}) to (\d{4}) individual local authority data - outturn$", r.get("title", ""), re.I)
        if m and int(m.group(1)) >= 2021:
            hits[f"{m.group(1)}-{m.group(2)[2:]}"] = r
    prev = json.loads(OUT["la-outturn"].read_text()) if OUT["la-outturn"].exists() else {"years": {}}
    years, errors = dict(prev.get("years", {})), []
    for fy, r in sorted(hits.items(), reverse=True)[:5]:
        try:
            doc = content(r["link"])
            if years.get(fy, {}).get("release_updated_at") == doc.get("public_updated_at"):
                continue
            att = attachment(doc, r"RSX")
            book = read_book(att["url"])
            sheet = next(k for k in book if k.upper().startswith("RSX_LA_DATA"))
            t = parse_rsx(book[sheet])
            if len(t["authorities"]) < 300 or len(t["services"]) < 8 or t["identity_failures"] > 20:
                raise RuntimeError(f"RSX failed validation ({len(t['authorities'])} authorities, {len(t['services'])} services, {t['identity_failures']} identity failures)")
            years[fy] = dict(dataset=r["title"], page=GOVUK + r["link"], attachment=att["url"], release_updated_at=doc.get("public_updated_at"), **t)
        except Exception as exc:
            errors.append(f"{fy}: {exc}")
    if not years:
        raise RuntimeError("; ".join(errors) or "No revenue outturn release found")
    return dict(publisher="Ministry of Housing, Communities and Local Government", page=GOVUK + "/government/collections/local-authority-revenue-expenditure-and-financing",
                attachment=years[max(years)]["attachment"], release_updated_at=years[max(years)]["release_updated_at"], errors=errors,
                caveats=["Revenue outturn: money actually spent on day-to-day services by English local authorities in the financial year, in £ thousand, nominal.",
                         "Net current expenditure is total expenditure minus sales, fees, charges and other income; it is not the same as the Council Tax requirement.",
                         "Capital spending (buildings, roads) is reported separately and is not included.",
                         "Authorities that did not return their form in time have no figures for that year; they are shown as not available, never as zero.",
                         "County and district councils in two-tier areas provide different services, so their totals are not comparable with unitary councils."],
                years=dict(sorted(years.items())))

TAC_PAGE = "https://www.england.nhs.uk/financial-accounting-and-reporting/nhs-providers-tac-data-publications/"
TAC_TABLES = {"A02CY01": "TAC02 SoCI", "A08CY01": "TAC08 Op Exp", "A06CY01": "TAC06 Op Inc 1"}


def tac_links(html):
    """Pair each year's TAC data files with the illustrative file listed just before them on the NHS England page."""
    years, illustrative = {}, None
    for href, text in re.findall(r'<a[^>]+href="([^"]+\.xlsx)"[^>]*>(.*?)</a>', html, re.I | re.S):
        text = re.sub(r"<[^>]+>|\s+", " ", text).strip()
        if "illustrative" in (href + text).lower():
            illustrative = href
            continue
        m = re.search(r"(\d{4})[/-](\d{2})", text) or re.search(r"(\d{4})-(\d{2})\.xlsx$", href)
        if not m:
            continue
        fy = f"{m.group(1)}-{m.group(2)}"
        kind = "foundation" if "foundation" in (href + text).lower() else "trust"
        years.setdefault(fy, {"illustrative": illustrative})[kind] = href
    return years


def tac_labels(book):
    """Subcode -> line label for the TAC sheets we publish, read from the year's illustrative form."""
    labels = {}
    for code, sheet in TAC_TABLES.items():
        df = book.get(sheet)
        if df is None:
            continue
        for i in range(len(df)):
            sub, label = df.iat[i, df.shape[1] - 1], df.iat[i, 1]
            if isinstance(sub, str) and re.match(r"^[A-Z]{3}\d{4}[A-Z]?$", sub.strip()) and isinstance(label, str):
                labels.setdefault(code, {})[sub.strip()] = re.sub(r"\s+", " ", label).strip()
    return labels


def parse_tac(book, kind):
    data = next(v for k, v in book.items() if k.strip().lower() == "all data")
    head = [re.sub(r"\s+", "", str(v)).lower() for v in data.iloc[0]]
    col = {h: j for j, h in enumerate(head)}
    col["total"] = col.get("total", col.get("valuenumber", len(head) - 1))
    plist = next((v for k, v in book.items() if "provider" in k.lower()), None)
    meta = {}
    if plist is not None:
        for i in range(1, len(plist)):
            name = plist.iat[i, 0]
            if isinstance(name, str) and name.strip():
                meta[name.strip().casefold()] = dict(code=str(plist.iat[i, 1]).strip(), region=str(plist.iat[i, 2]).strip(), sector=str(plist.iat[i, 3]).strip())
    orgs = {}
    for row in data.iloc[1:].itertuples(index=False):
        main = str(row[col["maincode"]]).strip()
        if main not in TAC_TABLES:
            continue
        name = str(row[col["organisationname"]]).strip()
        v = cell_number(row[col["total"]])
        o = orgs.setdefault(name, dict(name=name, type="NHS foundation trust" if kind == "foundation" else "NHS trust", **meta.get(name.casefold(), {}), values={}))
        o["values"].setdefault(main, {})[str(row[col["subcode"]]).strip()] = v
    return list(orgs.values())


def import_nhs_trust_accounts():
    curated = json.loads(Path("data/nhs/tac-sources.json").read_text())["years"]
    links, page_note = dict(curated), "curated list (data/nhs/tac-sources.json)"
    try:
        r = requests.get(TAC_PAGE, headers=UA, timeout=60)
        found = tac_links(r.text) if r.status_code == 200 else {}
        if found:
            links.update(found)
            page_note = "NHS England page"
        else:
            page_note += f"; the page returned HTTP {r.status_code} to an automated request"
    except requests.RequestException as exc:
        page_note += f"; page not reachable ({exc.__class__.__name__})"
    prev = json.loads(OUT["nhs-trust-accounts"].read_text()) if OUT["nhs-trust-accounts"].exists() else {"years": {}}
    years, errors = dict(prev.get("years", {})), []
    for fy in sorted(links, reverse=True)[:5]:
        L = links[fy]
        if years.get(fy, {}).get("files") == L:
            continue
        try:
            labels = tac_labels(read_book(L["illustrative"])) if L.get("illustrative") else {}
            orgs = []
            for kind in ("trust", "foundation"):
                if L.get(kind):
                    orgs += parse_tac(read_book(L[kind]), kind)
            bad = [o["name"] for o in orgs if None not in [o["values"].get("A02CY01", {}).get(c) for c in ("SCI0100A", "SCI0110A", "SCI0125A", "SCI0140A")]
                   and abs(sum(o["values"]["A02CY01"][c] for c in ("SCI0100A", "SCI0110A", "SCI0125A")) - o["values"]["A02CY01"]["SCI0140A"]) > 2]
            if len(orgs) < 150 or len(bad) > 5 or "A02CY01" not in labels:
                raise RuntimeError(f"TAC {fy} failed validation ({len(orgs)} providers, {len(bad)} with income - expenses != operating result, labels {list(labels)})")
            years[fy] = dict(files=L, labels=labels, providers=orgs, identity_failures=bad)
        except Exception as exc:
            errors.append(f"{fy}: {exc}")
    if not years:
        raise RuntimeError("; ".join(errors) or "No TAC data found")
    latest = max(years)
    return dict(dataset="NHS providers: trust accounts consolidation (TAC) data", publisher="NHS England", page=TAC_PAGE,
                attachment=years[latest]["files"].get("trust"), release_updated_at=None, errors=errors, links_from=page_note, unit="£ thousand, nominal", tables=TAC_TABLES,
                caveats=["Audited annual accounts data of NHS trusts and NHS foundation trusts in England, as submitted to NHS England for consolidation.",
                         "Figures are on each trust's group basis (including subsidiaries and charities it consolidates) and before NHS England's consolidation adjustments, so trusts cannot be added up to an NHS total without double counting payments between NHS bodies.",
                         "Operating expenses are shown as negative numbers in the statement of comprehensive income, as in the accounts.",
                         "Trusts that merged or were created in a year appear only for the years they existed; a missing trust is not a zero."],
                years=dict(sorted(years.items())))

def parse_grants_table1(df):
    """Table 1: department rows; Formula, General and Total blocks of financial-year columns, £ million."""
    hdr = next(i for i in range(min(len(df), 15)) if str(df.iat[i, 0]).strip().lower() == "department")
    blocks, current = [], None
    for j in range(1, df.shape[1]):
        b = df.iat[hdr - 1, j]
        if isinstance(b, str) and b.strip():
            current = b.strip()
        y = str(df.iat[hdr, j]).strip()
        if current and re.match(r"^\d{4}/\d{2}$", y):
            blocks.append((j, current.lower(), f"{y[:4]}-{y[5:]}"))
    years = sorted({y for _, _, y in blocks})
    rows = []
    for i in range(hdr + 1, len(df)):
        dept = df.iat[i, 0]
        if not isinstance(dept, str) or not dept.strip():
            continue
        if re.match(r"^(source|note)", dept.strip(), re.I):
            break
        vals = {}
        for j, b, y in blocks:
            vals.setdefault(b, {})[y] = cell_number(df.iat[i, j])
        rows.append(dict(department=dept.strip(), values={b: [v.get(y) for y in years] for b, v in vals.items()}))
    return dict(unit="£ million", years=years, rows=rows)


def txt(v):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def grant_id(v, width=0):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = str(v).strip()
    if t.endswith(".0"):
        t = t[:-2]
    if not t or t.lower() in ("nan", "none", "n/a", "0"):
        return None
    return t.zfill(width) if width and t.isdigit() else t


def header_frame(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    return df.iloc[1:]


GRANT_RECIPIENT_MIN = 100000  # recipients listed on the site; smaller recipients are counted in the totals only


def import_grants():
    q = requests.get(GOVUK + "/api/search.json", headers=UA, timeout=60, params={"q": "Government grants statistics", "count": 30, "fields": "title,link"}).json()
    hits = [r for r in q.get("results", []) if re.match(r"government grants statistics \d{4} to \d{4}$", r.get("title", ""), re.I)
            and r.get("link", "").startswith("/government/statistics/") and "/announcements/" not in r.get("link", "")]
    hits.sort(key=lambda r: r["title"][-12:], reverse=True)
    if not hits:
        raise RuntimeError("No government grants statistics release found")
    r = hits[0]
    doc = content(r["link"])
    m = re.search(r"(\d{4}) to (\d{4})$", r["title"])
    fy = f"{m.group(1)}-{m.group(2)[2:]}"
    t1 = parse_grants_table1(read_book(attachment(doc, r"statistical tables")["url"])["Table_1"])
    reg_att = attachment(doc, r"Grants Register")
    book = read_book(reg_att["url"], engine="calamine")
    sch = header_frame(book["#Schemes"])
    schemes = []
    for row in sch.itertuples(index=False):
        d = dict(zip(sch.columns, row))
        v = cell_number(d.get("FY value"))
        if not isinstance(d.get("Grant Programme:Title"), str):
            continue
        schemes.append([d.get("Grant Programme:Code"), d["Grant Programme:Title"].strip(), (d.get("Funding Org:Name") or "").strip(),
                        (d.get("Managed by: Organisation Name") or "").strip() if isinstance(d.get("Managed by: Organisation Name"), str) else None,
                        v, d.get("Allocation method") if isinstance(d.get("Allocation method"), str) else None,
                        d.get("COFOG: Sector type") if isinstance(d.get("COFOG: Sector type"), str) else None])
    recipients, awards, n_awards = {}, [], 0
    for sheet, df in book.items():
        if sheet.startswith("#") or sheet == "Meta" or df.shape[1] < 20:
            continue
        a = header_frame(df)
        if "Amount Awarded" not in a.columns:
            continue
        for row in a.itertuples(index=False):
            d = dict(zip(a.columns, row))
            amt = cell_number(d.get("Amount Awarded"))
            name = d.get("Recipient Org:Name")
            if amt is None or not isinstance(name, str):
                continue
            n_awards += 1
            rid = txt(d.get("Recipient Org:Identifier"))
            coh = grant_id(d.get("Recipient Org:Company Number"), 8)
            chc = grant_id(d.get("Recipient Org:Charity Number"))
            if rid.upper().startswith("GB-COH-"):
                coh = coh or rid[7:].strip().zfill(8)
            # Group by a published identifier only; awards without one are kept apart per identifier-less name.
            key = ("GB-COH-" + coh) if coh else rid if rid and not rid.startswith("360G-") else f"{rid or 'noid'}|{name.strip().casefold()}"
            rec = recipients.setdefault(key, dict(name=name.strip(), coh=None, chc=None, total=0.0, n=0, funders=set(), schemes=set()))
            rec["total"] += amt
            rec["n"] += 1
            rec["funders"].add(txt(d.get("Funding Org:Name")))
            rec["schemes"].add(txt(d.get("Grant Programme:Title")))
            rec["coh"] = rec["coh"] or coh
            rec["chc"] = rec["chc"] or chc
            awards.append([amt, txt(d.get("Title"))[:160], name.strip(), txt(d.get("Funding Org:Name")),
                           txt(d.get("Grant Programme:Title"))[:160], str(d.get("Award Date") or "")[:10], d.get("Allocation Method") if isinstance(d.get("Allocation Method"), str) else None, key])
    if len(schemes) < 100 or n_awards < 1000 or len(t1["rows"]) < 10:
        raise RuntimeError(f"Grants register failed validation ({len(schemes)} schemes, {n_awards} awards, {len(t1['rows'])} departments)")
    rec_rows = sorted(([k, v["name"], v["coh"], v["chc"], round(v["total"], 2), v["n"], sorted(f for f in v["funders"] if f)[:3], sorted(s for s in v["schemes"] if s)[:3]]
                       for k, v in recipients.items()), key=lambda x: -x[4])
    awards.sort(key=lambda a: -a[0])
    return dict(dataset=r["title"], publisher="Cabinet Office (Government Grants Information System)", page=GOVUK + r["link"], attachment=reg_att["url"],
                release_updated_at=doc.get("public_updated_at"), financial_year=fy, departments=t1,
                schemes=dict(fields=["code", "title", "funder", "managed_by", "fy_value_gbp", "allocation_method", "cofog"], rows=sorted(schemes, key=lambda s: -(s[4] or 0))),
                recipients=dict(fields=["key", "name", "company_number", "charity_number", "awarded_gbp", "awards", "funders", "schemes"], rows=[x for x in rec_rows if x[4] >= GRANT_RECIPIENT_MIN], total_recipients=len(rec_rows),
                                min_awarded_gbp=GRANT_RECIPIENT_MIN, total_awarded_gbp=round(sum(x[4] for x in rec_rows), 2)),
                awards=dict(fields=["amount_gbp", "title", "recipient", "funder", "scheme", "award_date", "allocation_method", "recipient_key"], rows=awards[:2000], total_awards=n_awards),
                caveats=["Grant spending by department (Table 1) is money paid in each financial year, in £ million.",
                         "Scheme values are the scheme's spending in the financial year. Award amounts are the value of each award as recorded, which can cover several years and is not the same as money paid in this year.",
                         "Recipients are grouped only by their published identifier (Companies House, charity or other register). Organisations without an identifier are not merged with others of the same name.",
                         "Formula grants (for example to councils and schools) are mostly shown as totals by department; the register lists awards only where departments publish them.",
                         "Covers UK government departments' grants as reported to the Government Grants Information System; devolved governments' grants are not included."])


STATSWALES_API = "https://api.stats.gov.wales/v1/"
WALES_LA_OUTTURN = "213aeb99-18eb-42c9-b00e-e4b716e82cdf"  # Revenue outturn expenditure by authority and service


def statswales(dataset_id):
    """Metadata and the full CSV of one dataset from the StatsWales API."""
    meta = requests.get(STATSWALES_API + dataset_id, headers=UA, timeout=60)
    meta.raise_for_status()
    r = requests.get(STATSWALES_API + dataset_id + "/download/csv", headers=UA, timeout=180)
    r.raise_for_status()
    import csv
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    return meta.json(), rows


WALES_GROUPS = [("Total", "total"), ("NPA", "National park authority"), ("Police", "Police"), ("Fire", "Fire and rescue authority")]


def parse_wales_outturn(rows):
    """StatsWales revenue outturn CSV (long format) -> per-authority, per-year service values in £ thousand.
    Blank cells stay None.  Checks that the services add up to the published 'Revenue expenditure' line."""
    years, services, auth = set(), [], {}
    for r in rows:
        if r.get("Data description") != "£ thousand":
            continue
        name, fy, svc = r["Authority"].strip(), r["Year"].strip(), r["Service"].strip()
        v = r["Data values"].strip()
        years.add(fy)
        if svc not in services:
            services.append(svc)
        a = auth.setdefault(name, {"name": name, "values": {}})
        a["values"].setdefault(fy, {})[svc] = float(v) if v not in ("", "..", ".", "*") else None
    total = "Revenue expenditure"
    if total not in services:
        raise RuntimeError("StatsWales outturn has no 'Revenue expenditure' total")
    services.remove(total)
    services.append(total)
    failures = 0
    for a in auth.values():
        n = a["name"]
        a["group"] = next((g for key, g in WALES_GROUPS if key in n), "Unitary authority")
        for fy, vals in a["values"].items():
            t = vals.get(total)
            parts = [vals.get(sv) for sv in services[:-1]]
            if t is not None and all(x is not None for x in parts) and abs(sum(parts) - t) > 1:
                failures += 1
    return dict(years=sorted(years), services=services, authorities=sorted(auth.values(), key=lambda a: (a["group"] != "Unitary authority", a["group"], a["name"])),
                identity_failures=failures)


def import_wales_la_outturn():
    meta, rows = statswales(WALES_LA_OUTTURN)
    rev = meta.get("published_revision") or {}
    en = next((m for m in rev.get("metadata", []) if m.get("language") == "en-GB"), {})
    t = parse_wales_outturn(rows)
    unitary = [a for a in t["authorities"] if a["group"] == "Unitary authority"]
    if len(unitary) != 22 or len(t["years"]) < 5 or t["identity_failures"]:
        raise RuntimeError(f"Wales outturn failed validation ({len(unitary)} unitary authorities, {len(t['years'])} years, {t['identity_failures']} identity failures)")
    page = next((l["url"] for l in rev.get("related_links", []) if "outturn" in l.get("url", "")), "https://www.gov.wales/local-authority-revenue-and-capital-outturn-expenditure")
    return dict(publisher="Welsh Government (StatsWales)", dataset=en.get("title", "Revenue outturn expenditure by authority and service"),
                page=page, statswales="https://stats.gov.wales/en-GB/" + WALES_LA_OUTTURN,
                attachment=STATSWALES_API + WALES_LA_OUTTURN + "/download/csv", release_updated_at=rev.get("publish_at"),
                unit="£ thousand", caveats=[
                    "Revenue outturn: what Welsh local authorities actually spent on day-to-day services in the financial year, in £ thousand, nominal, as published by the Welsh Government.",
                    en.get("summary", "").strip(),
                    "The Welsh and English returns define their service lines and totals differently, so a Welsh figure is not directly comparable with an English council's figure.",
                    "Police, fire and national park authorities are separate bodies; the Wales total is the Welsh Government's published total, not a sum calculated here.",
                    "Capital spending is not included. Blank cells in the source are shown as not available, never as zero."],
                **t)


WALES_NHS_PROGRAMME = "2f4e637b-4622-4ad0-b2a3-15901c41147e"  # NHS expenditure by programme budget category, organisation and commissioner
# Programme categories that the source breaks down further; the parts must add up to the parent.
WALES_PB_PARTS = {
    "Endocrine, nutritional & metabolic problems": ["Diabetes", "Other endocrine, nutritional and metabolic problems"],
    "Mental health problems": ["General mental illness", "Elderly mental illness", "Child & adolescent mental health services", "Other mental health problems"],
    "Circulation problems": ["Coronary Heart Disease", "Cerebrovascular disease", "Other problems of circulation"],
    "Genito Urinary system disorders (exc infertility)": ["Genital tract problems", "Renal problems", "Chronic renal failure", "Sexually transmitted infections",
                                                          "Other problems of the genito urinary system"],
    "Other": ["General medical services", "Open access", "Continuing care", "Other PHW functions", "Other expenditure"],
}
WALES_PB_OF_WHICH = {}  # categories shown as 'of which' without an additivity check (none at present)


def parse_wales_programme(rows):
    """StatsWales programme budget CSV -> {org: {year: {commissioner: {category: £000}}}} with hierarchy checks."""
    cats, orgs, years, comms = [], {}, set(), []
    for r in rows:
        if r.get("Data description") != "Expenditure (£000)":
            continue
        org, fy, cat, com = (r[k].strip() for k in ("Organisation", "Year", "Programme category", "Commissioner"))
        v = r["Data values"].strip()
        if cat not in cats:
            cats.append(cat)
        if com not in comms:
            comms.append(com)
        years.add(fy)
        orgs.setdefault(org, {}).setdefault(fy, {}).setdefault(com, {})[cat] = float(v) if v not in ("", "..", ".", "*") else None
    if "Total" not in cats:
        raise RuntimeError("Programme budget data has no Total category")
    children = {c for parts in WALES_PB_PARTS.values() for c in parts} | set(WALES_PB_OF_WHICH)
    top = [c for c in cats if c != "Total" and c not in children]
    failures, part_issues, checked = [], [], 0
    for org, ys in orgs.items():
        for fy, cs in ys.items():
            for com, v in cs.items():
                for parent, parts in [("Total", top)] + list(WALES_PB_PARTS.items()):
                    vals = [v.get(p) for p in parts]
                    if v.get(parent) is None or any(x is None for x in vals):
                        continue
                    checked += 1
                    if abs(sum(vals) - v[parent]) > 5:
                        issue = dict(organisation=org, year=fy, commissioner=com, category=parent, parts_sum=round(sum(vals), 1), published=round(v[parent], 1))
                        (failures if parent == "Total" else part_issues).append(issue)
    # The conditions must always add up to the total.  A breakdown that does not add up to its parent
    # (2015-16 endocrine problems, for example) is a fault in the source: it is kept and flagged, not hidden.
    return dict(categories=cats, top_level=top, parts=WALES_PB_PARTS, of_which=WALES_PB_OF_WHICH, commissioners=comms,
                years=sorted(years), organisations=orgs, checks=checked, identity_failures=failures[:20], identity_failure_count=len(failures),
                breakdown_issues=part_issues)


def import_wales_nhs_programme():
    meta, rows = statswales(WALES_NHS_PROGRAMME)
    rev = meta.get("published_revision") or {}
    en = next((m for m in rev.get("metadata", []) if m.get("language") == "en-GB"), {})
    t = parse_wales_programme(rows)
    if "Wales" not in t["organisations"] or len(t["years"]) < 5 or t["checks"] < 100 or t["identity_failure_count"] or len(t["breakdown_issues"]) > t["checks"] * 0.02:
        raise RuntimeError(f"Wales programme budgets failed validation ({len(t['years'])} years, {t['checks']} checks, {t['identity_failure_count']} total failures, {len(t['breakdown_issues'])} breakdown issues: {(t['identity_failures'] or t['breakdown_issues'])[:3]})")
    page = next((l["url"] for l in rev.get("related_links", []) if l.get("url")), "https://www.gov.wales/nhs-expenditure-programme-budgets")
    return dict(publisher="Welsh Government (StatsWales)", dataset=en.get("title"), page=page, statswales="https://stats.gov.wales/en-GB/" + WALES_NHS_PROGRAMME,
                attachment=STATSWALES_API + WALES_NHS_PROGRAMME + "/download/csv", release_updated_at=rev.get("publish_at"), unit="£ thousand",
                caveats=[en.get("summary", "").strip(),
                         "Programme budgeting assigns NHS spending to the health condition it treats, as estimated by each health board from its own costing data; it is an analysis of spending, not a separate budget.",
                         "Figures are £ thousand, nominal (not adjusted for inflation). Health boards were reorganised in 2019 (Abertawe Bro Morgannwg became Swansea Bay, Cwm Taf became Cwm Taf Morgannwg), so their series break.",
                         "Breakdowns such as Diabetes under Endocrine problems are parts of the line above and are never added to it. Every year is checked: the conditions add up to the published total. Where a published breakdown does not add up to its line, the table says so; the figures are shown as published.",
                         "This series covers the NHS in Wales only."],
                **t)


IMPORTERS = {"hmrc-receipts": import_hmrc_receipts, "pss-tes": import_pss, "cra": import_cra, "council-tax": import_council_tax,
             "dwp-benefits": import_dwp_benefits, "la-outturn": import_la_outturn,
             "nhs-trust-accounts": import_nhs_trust_accounts, "grants": import_grants,
             "wales-la-outturn": import_wales_la_outturn, "wales-nhs-programme": import_wales_nhs_programme}


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
