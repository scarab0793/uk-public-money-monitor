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
       "la-outturn": Path("data/local-government/revenue-outturn-england.json")}
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


IMPORTERS = {"hmrc-receipts": import_hmrc_receipts, "pss-tes": import_pss, "cra": import_cra, "council-tax": import_council_tax,
             "dwp-benefits": import_dwp_benefits, "la-outturn": import_la_outturn}


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
