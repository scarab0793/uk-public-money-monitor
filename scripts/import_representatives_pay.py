"""Import what MPs are paid and what IPSA pays for their parliamentary work.

  IPSA annual publication (https://www.theipsa.org.uk/mp-costs/annual-publication/)
    otherInfo                MP salary actually paid, additional salary (committee chairs, Panel of Chairs),
                             London Area Living Payment, resettlement / loss-of-office payments
    totalSpend               budgets and spend by heading (office, staffing, winding-up, accommodation,
                             travel and subsistence, other costs)
    individualBusinessCosts  every claim; aggregated here by IPSA category and cost type (net of repayments)
  IPSA pay page              the MP salary and committee chair salary rates by year
  GOV.UK ministerial-salary-data  ministerial salaries paid on top of the MP salary

Years are discovered from the IPSA download links, so a new financial year is picked up without code
changes.  A source that fails keeps its previous output; the failure goes to the report file.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


IPSA = "https://www.theipsa.org.uk"
GOVUK = "https://www.gov.uk"
UA = {"User-Agent": "uk-public-money-monitor/1.0 (+https://github.com/scarab0793/uk-public-money-monitor)"}
OUT_DIR = Path("data/representatives")
INDEX = OUT_DIR / "mps-index.json"
REPORT = OUT_DIR / "import-report.json"
YEARS_KEPT = 5
SECTIONS = [("office", r"office"), ("staffing", r"staffing"), ("winding_up", r"wind(?:ing)?-up"),
            ("accommodation", r"accommodation"), ("travel", r"travel and subsistence"), ("other", r"other costs")]


def get(url, **kw):
    import requests  # imported lazily so the parsers can be tested with the standard library only
    r = requests.get(url, headers=UA, timeout=300, **kw)
    r.raise_for_status()
    return r


def money(v):
    """'£1,234.56' -> 1234.56; '-£5.00' -> -5.0; 'N/A' and blanks -> None (unknown, not zero)."""
    s = (v or "").strip().replace(",", "").replace("£", "")
    if not s or s.upper() in ("N/A", "NA", "-"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def text(v):
    s = (v or "").strip()
    return None if not s or s.upper() == "N/A" else s


def read_csv(body):
    body = body.lstrip("﻿")
    return list(csv.reader(io.StringIO(body)))


def fy_label(code):
    """'25_26' -> '2025-26'."""
    a, b = code.split("_")
    return f"20{a}-{b}"


def discover_years(page_html):
    years = {}
    for t, y in re.findall(r"type=(\w+)(?:&amp;|&)year=(\d\d_\d\d)", page_html):
        years.setdefault(y, set()).add(t)
    return years


def parse_total_spend(rows):
    """Budgets and spend by heading.  Column names changed over the years (2021-22 says 'maximum budget
    available', later years '(uncapped)'), so columns are read in order under the heading they belong to."""
    head = [h.strip() for h in rows[0]]
    out = {}
    for r in rows[1:]:
        if len(r) < len(head) - 1 or not r[0].strip():
            continue
        rec = dict(name=r[0].strip(), id=r[-1].strip(), budgets={})
        section = None
        for h, v in zip(head, r):
            lh = h.lower()
            if lh.startswith(("subtotal", "overall")):
                continue
            if "constituency" in lh:
                if text(v):
                    rec["constituency"] = text(v)
                continue
            key = next((k for k, pat in SECTIONS if re.match(pat, lh)), None)
            if key:
                section = key
            if not section:
                continue
            b = rec["budgets"].setdefault(section, {})
            if lh.startswith("reason"):
                b["reason"] = text(v)
            elif "remaining" in lh:
                b["remaining"] = money(v)
            elif "spend" in lh or "uncapped" in lh:
                b["spend"] = money(v)
            elif "budget" in lh:
                b["budget"] = money(v)
        out[rec["id"]] = rec
    return out


def parse_other_info(rows):
    head = [h.strip().lstrip("﻿") for h in rows[0]]
    col = lambda r, name: r[head.index(name)] if name in head and head.index(name) < len(r) else ""
    out = {}
    for r in rows[1:]:
        if len(r) < 8 or not r[0].strip():
            continue
        pid = col(r, "pID").strip()
        out[pid] = dict(
            name=r[0].strip(), constituency=text(col(r, "Constituency")),
            basic_salary=money(col(r, "Basic salary")), additional_salary=money(col(r, "Additional salary")),
            additional_salary_reason=text(col(r, "Reason for additional salary")),
            resettlement=money(col(r, "Resettlement/Loss-of-office Payment")),
            lalp=money(col(r, "LALP amount")), lalp_period=text(col(r, "LALP period")),
            connected_party=[x for x in [text(col(r, "Connected party name")), text(col(r, "Connected party job title")), text(col(r, "Connected party salary"))] if x],
            contingency_granted=money(col(r, "Contingency amount granted")),
            staff_reward_payments=money(col(r, "Reward and recognition payments")),
            debts_written_off=money(col(r, "Debts incurred by the MP which IPSA has written off")))
    return out


def aggregate_claims(body):
    """Sum every claim by MP, IPSA category and cost type, net of amounts repaid."""
    reader = csv.reader(io.StringIO(body.lstrip("﻿")))
    head = [h.strip() for h in next(reader)]
    i = {k: head.index(k) for k in ("Parliamentary ID", "Category", "Cost Type", "Amount Paid", "Amount Repaid", "Amount Not Paid")}
    out, n = {}, 0
    for r in reader:
        if len(r) < len(head) - 2:
            continue
        n += 1
        pid, cat, typ = r[i["Parliamentary ID"]].strip(), r[i["Category"]].strip(), r[i["Cost Type"]].strip() or "Other"
        net = (money(r[i["Amount Paid"]]) or 0) - (money(r[i["Amount Repaid"]]) or 0)
        m = out.setdefault(pid, dict(claims=0, not_paid=0.0, by_category={}))
        m["claims"] += 1
        m["not_paid"] += money(r[i["Amount Not Paid"]]) or 0
        c = m["by_category"].setdefault(cat, {})
        c[typ] = c.get(typ, 0) + net
    for m in out.values():
        m["not_paid"] = round(m["not_paid"], 2)
        for c in m["by_category"].values():
            for k in c:
                c[k] = round(c[k], 2)
    return out, n


def build_year(code):
    q = f"{IPSA}/api/download?year={code}&type="
    spend = parse_total_spend(read_csv(get(q + "totalSpend").text))
    info = parse_other_info(read_csv(get(q + "otherInfo").text))
    claims, n_claims = aggregate_claims(get(q + "individualBusinessCosts").text)
    if len(spend) < 600 or len(info) < 600:
        raise RuntimeError(f"{code}: only {len(spend)} budget rows and {len(info)} pay rows")
    mps, totals = [], {}
    for pid in sorted(set(spend) | set(info), key=lambda p: (info.get(p) or spend.get(p))["name"]):
        s, o, c = spend.get(pid, {}), info.get(pid, {}), claims.get(pid)
        rec = dict(id=pid, name=o.get("name") or s.get("name"), constituency=o.get("constituency") or s.get("constituency"),
                   pay={k: o.get(k) for k in ("basic_salary", "additional_salary", "additional_salary_reason", "resettlement", "lalp", "lalp_period")},
                   budgets=s.get("budgets", {}),
                   other={k: o.get(k) for k in ("connected_party", "contingency_granted", "staff_reward_payments", "debts_written_off") if o.get(k)})
        if c:
            rec["claims"] = c
        mps.append(rec)
        for k in ("basic_salary", "additional_salary", "resettlement", "lalp"):
            totals[k] = totals.get(k, 0) + (o.get(k) or 0)
        for k, b in rec["budgets"].items():
            totals["spend_" + k] = totals.get("spend_" + k, 0) + (b.get("spend") or 0)
    # Reconciliation: claims grouped by IPSA category against the spend IPSA reports for each budget.  They
    # are close but not identical (some costs are charged to a different budget than their claim category).
    cat_map = {"office": ["Office Costs"], "staffing": ["Staffing"], "accommodation": ["Accommodation"], "winding_up": ["Winding Up"],
               "travel": ["MP Travel", "Staff Travel", "Dependant Travel"], "other": ["Miscellaneous"]}
    recon = {}
    for k, cats in cat_map.items():
        claimed = sum(sum(v.values()) for m in claims.values() for cat, v in m["by_category"].items() if cat in cats)
        recon[k] = dict(budget_spend=round(totals.get("spend_" + k, 0), 2), claims=round(claimed, 2))
    return dict(year=fy_label(code), code=code, mps=mps, totals={k: round(v, 2) for k, v in totals.items()},
                claims_reconciliation=recon, claim_rows=n_claims,
                files={t: q + t for t in ("otherInfo", "totalSpend", "individualBusinessCosts")})


class Tables(HTMLParser):
    """Collect the cell text of every <table> in a page."""
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).replace("​", "").strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def tables(page):
    p = Tables()
    p.feed(page)
    return p.tables


def pound(s):
    m = re.search(r"£\s?([\d,]+(?:\.\d+)?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def salary_rates():
    page = get(IPSA + "/mps-pay-and-pensions").text
    mp, chairs = [], []
    for t in tables(page):
        head = " ".join(t[0]).lower() if t else ""
        rows = [[r[0], pound(r[1])] for r in t[1:] if len(r) >= 2 and pound(r[1])]
        if "annual salary" in head:
            mp = rows
        elif head.startswith("year") and "salary" in head and not chairs:
            chairs = rows
    if not mp or not re.search(r"\d{4}", mp[0][0]):
        raise RuntimeError("MP salary table not found on the IPSA pay page")
    return dict(page=IPSA + "/mps-pay-and-pensions", mp_salary=mp, committee_chair_salary=chairs)


def ministerial_salaries():
    doc = get(GOVUK + "/api/content/government/publications/ministerial-salary-data").json()
    att = next(a for a in doc["details"]["attachments"] if not (a.get("content_type") or "").startswith("application/"))
    page = get(GOVUK + "/api/content" + att["url"]).json()
    sections = []
    body = page["details"]["body"]
    heads = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S)
    for i, t in enumerate(tables(body)):
        rows = []
        for r in t[1:]:
            if len(r) >= 3 and pound(r[1]):
                posts = [p.strip() for p in re.split(r"\s+-\s+|^-\s*", r[0]) if p.strip()]
                rows.append(dict(posts=posts, entitled=pound(r[1]), claimed=pound(r[2])))
        title = html.unescape(re.sub(r"<[^>]+>", "", heads[i])).strip() if i < len(heads) else f"Table {i + 1}"
        sections.append(dict(title=re.sub(r"^\d+\.\s*", "", title), rows=rows))
    if not sections or not sections[0]["rows"]:
        raise RuntimeError("Ministerial salary tables not found")
    return dict(title=page["title"], page=GOVUK + att["url"], release_updated_at=page.get("public_updated_at"), sections=sections)


def write_if_changed(path, payload):
    old = json.loads(path.read_text()) if path.exists() else None
    strip = lambda d: {k: v for k, v in (d or {}).items() if k != "retrieved_at"}
    if old and strip(old) == strip(payload):
        return "unchanged"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return "updated"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    ok = 0

    def step(name, fn):
        nonlocal ok
        try:
            status = fn()
            report[name] = dict(status=status, checked_at=now)
            ok += 1
        except Exception as exc:  # keep the previous output
            report[name] = dict(report.get(name, {}), status="failed_kept_previous", checked_at=now, error=str(exc)[:500])
        print(name, report[name]["status"], report[name].get("error", ""), flush=True)

    years = discover_years(get(IPSA + "/mp-costs/annual-publication/").text)
    complete = sorted((y for y, t in years.items() if {"totalSpend", "otherInfo", "individualBusinessCosts"} <= t), reverse=True)[:YEARS_KEPT]
    if not complete:
        raise SystemExit("No IPSA years found on the annual publication page")
    summaries = {s["year"]: s for s in index.get("years", [])}

    for code in complete:
        def do(code=code):
            y = build_year(code)
            y["retrieved_at"] = now
            status = write_if_changed(OUT_DIR / f"mps-{y['year']}.json", y)
            summaries[y["year"]] = dict(year=y["year"], file=f"data/representatives/mps-{y['year']}.json", mps=len(y["mps"]),
                                        totals=y["totals"], claims_reconciliation=y["claims_reconciliation"])
            return status
        step("ipsa-" + code, do)

    def rates():
        index["rates"] = salary_rates()
        return "updated"
    step("ipsa-salary-rates", rates)

    def ministers():
        index["ministerial_salaries"] = ministerial_salaries()
        return "updated"
    step("ministerial-salaries", ministers)

    index.update(publisher="Independent Parliamentary Standards Authority (IPSA); Cabinet Office",
                 page=IPSA + "/mp-costs/annual-publication/", retrieved_at=now,
                 years=[summaries[k] for k in sorted(summaries, reverse=True) if (OUT_DIR / f"mps-{k}.json").exists()])
    INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
