"""Import what councillors were paid, by heading, from each council's own statutory publication.

Every council in England must publish, each year, the total paid to each councillor under each heading of its
members' allowances scheme (basic allowance, special responsibility allowance, travel and subsistence, ...):
regulation 15 of the Local Authorities (Members' Allowances) (England) Regulations 2003.  There is no national
collection, so each council's own file is read.  The registry data/representatives/council-sources.json lists
the councils, the page that links to their annual statement and how to recognise it; the newest year's link is
picked automatically, so the next year's statement is found without code changes.

Files come as spreadsheets, web-page tables or PDFs; all three are turned into a grid of cells and read the same
way: the header row names the council's own headings, every row under it with a councillor's name and amounts
becomes one councillor.  Where the council publishes a total column, each row is checked against the sum of its
parts.  A council that fails keeps its previous figures; the failure is recorded in the report.

  python scripts/import_council_allowances.py              all councils in the registry
  python scripts/import_council_allowances.py --grid URL   print the grid read from one file (diagnostic)
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import requests

UA = {"User-Agent": "uk-public-money-monitor/1.0 (+https://github.com/scarab0793/uk-public-money-monitor)"}
REGISTRY = Path("data/representatives/council-sources.json")
OUT = Path("data/representatives/councillors.json")
REPORT = Path("data/representatives/councils-report.json")

NUM_RE = re.compile(r"^\(?-?£?\s?-?\d[\d,]*(?:\.\d+)?\)?$|^-$|^–$|^£?\s?-$|^nil$", re.I)
CATEGORIES = [  # (category, pattern on the council's own heading), first match wins
    ("basic", r"basic|^members?'? allowances?\b(?! scheme)"),
    ("special_responsibility", r"special|\bsra\b|responsib"),
    ("civic", r"chair(man)?'?s? allowance|civic|mayor|vice.?chair"),
    ("carers", r"carer|dependant|dependent|childcare|care allowance"),
    ("travel", r"travel|mileage|car\b|fares|rail|train|bus|taxi|parking|motor|bicycle|transport"),
    ("subsistence", r"subsistence|meal|accommodation|hotel|overnight"),
    ("ict", r"\bict\b|broadband|telephone|phone|internet|computer|it allowance"),
    ("co_opted", r"co-?opted"),
    ("other", r"."),
]
NOT_A_NAME = re.compile(r"^(total|grand total|sub.?total|totals|overall|sum|councillor name|name|member|members)$", re.I)


def get(url, **kw):
    for attempt in range(2):
        r = requests.get(url, headers=UA, timeout=(15, 60), **kw)
        if r.status_code < 500 and r.status_code != 403 or attempt == 1:
            break
        __import__("time").sleep(5)
    r.raise_for_status()
    return r


def amount(cell):
    s = str(cell).strip().replace("£", "").replace(",", "").replace(" ", "")
    if s in ("-", "–", "", "nil", "Nil", "NIL"):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def is_amount(cell):
    s = str(cell).strip()
    return bool(s) and bool(NUM_RE.match(s.replace(" ", "")))


TOTAL_WORDS = r"(grand|overall|sum|total|totals|paid|claimed|amount|amounts|allowances?|payments?|expenses|and|of|cost|costs|er|£|annual|for|the|year|\(\d+\)|\W)"


def category(label):
    """Map a council's own heading to a common category.  'Total', 'Total allowances and expenses', 'Total ER Cost'
    are totals; 'Total Basic Allowance' is the basic allowance."""
    l = label.lower().strip()
    if re.search(r"\btotal|\bsum\b", l) and re.fullmatch(rf"(?:{TOTAL_WORDS}\s*)+", l):
        return "total"
    return next(c for c, pat in CATEGORIES if re.search(pat, l))


# ---------------------------------------------------------------- files to grids

def grid_from_sheet(content):
    import pandas as pd
    books = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
    grids = []
    for name, df in books.items():
        rows = [["" if (v is None or (isinstance(v, float) and v != v)) else (f"{v:.2f}" if isinstance(v, float) else str(v)).strip() for v in r]
                for r in df.itertuples(index=False)]
        grids.append(rows)
    return grids


def grid_from_csv(text):
    import csv
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(text.lstrip("﻿")))]


class _Tables(__import__("html.parser").parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.row, self.cell, self.span = [], None, None, 1

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell, self.span = [], int(dict(attrs).get("colspan") or 1)
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.extend([re.sub(r"\s+", " ", "".join(self.cell)).strip()] + [""] * (self.span - 1))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                self.tables[-1].append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def grids_from_html(text):
    p = _Tables()
    p.feed(text)
    return [t for t in p.tables if len(t) > 3]


def grid_from_pdf(content):
    """Word positions (pdftotext -bbox) are used, so columns line up across pages even where a page has no header.
    Column positions come from the right edges of the amounts in the data rows; the header words above the first
    data row are attached to the column whose centre they are nearest."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(content)
        f.flush()
        xml = subprocess.run(["pdftotext", "-bbox", f.name, "-"], capture_output=True, text=True, check=True).stdout
    pages = []
    for page in re.findall(r"<page[^>]*>(.*?)</page>", xml, re.S):
        words = [(float(a), float(b), float(c), float(d), htmllib.unescape(t)) for a, b, c, d, t in
                 re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', page)]
        pages.append(words)
    return grid_from_words(pages)


def grid_from_words(pages):
    """pages: lists of (x0, y0, x1, y1, text).  Returns one grid.  Some statements lay out each page at a different
    width; every page's x positions are rescaled so its first and last amount columns line up with the first page's."""
    def span(words):
        ends = [x1 for x0, y0, x1, y1, t in words if is_amount(t) and re.search(r"£|\d\.\d\d\)?$", t)]  # not page numbers
        return (min(ends), max(ends)) if len(ends) >= 4 else None
    ref = next((span(w) for w in pages if span(w)), None)
    if ref:
        scaled = []
        for words in pages:
            sp = span(words)
            if sp and sp[1] - sp[0] > 20 and ref[1] - ref[0] > 20 and (abs(sp[0] - ref[0]) > 4 or abs(sp[1] - ref[1]) > 4):
                k = (ref[1] - ref[0]) / (sp[1] - sp[0])
                f = lambda x: ref[0] + (x - sp[0]) * k
                words = [(f(x0), y0, f(x1), y1, t) for x0, y0, x1, y1, t in words]
            scaled.append(words)
        pages = scaled
    lines = []  # (page, y, [tokens (x0, x1, text)])
    for pi, words in enumerate(pages):
        rows = {}
        for x0, y0, x1, y1, t in sorted(words, key=lambda w: (round(w[1]), w[0])):
            key = next((k for k in rows if abs(k - y0) <= 2.5), y0)
            rows.setdefault(key, []).append((x0, x1, t))
        for y in sorted(rows):
            ws = sorted(rows[y])
            toks = []
            for x0, x1, t in ws:  # words closer than ~a space apart form one cell
                if toks and x0 - toks[-1][1] < 4.5 and not (is_amount(t) and is_amount(toks[-1][2])) and not (is_amount(t) != is_amount(toks[-1][2]) and x0 - toks[-1][1] > 2.5):
                    toks[-1] = (toks[-1][0], x1, toks[-1][2] + " " + t)
                else:
                    toks.append((x0, x1, t))
            lines.append((pi, y, toks))
    amounts_of = lambda toks: [t for t in toks if is_amount(t[2])]
    data = [i for i, (_, _, toks) in enumerate(lines) if len(amounts_of(toks)) >= 1 and toks and not is_amount(toks[0][2])
            and re.match(r"[A-Za-z]", toks[0][2]) and toks[0][0] < min(t[0] for t in amounts_of(toks))]
    # keep rows that look like the table: at least two amounts, or one amount in an already-known column
    multi = [i for i in data if len(amounts_of(lines[i][2])) >= 2]
    if len(multi) < 3:
        return []
    ends = sorted(t[1] for i in multi for t in amounts_of(lines[i][2]))
    cols = []
    for e in ends:
        if cols and e - cols[-1][-1] <= 6:
            cols[-1].append(e)
        else:
            cols.append([e])
    rights = [sorted(c)[len(c) // 2] for c in cols if len(c) >= 2]
    data = [i for i in data if all(min(abs(r - t[1]) for r in rights) <= 8 for t in amounts_of(lines[i][2]))]
    first = data[0]
    first_amount_x = min(t[0] for i in data for t in amounts_of(lines[i][2]))
    centres = []
    for r in rights:
        xs = [(t[0] + t[1]) / 2 for i in data for t in amounts_of(lines[i][2]) if abs(t[1] - r) <= 8]
        centres.append(sum(xs) / len(xs) if xs else r - 20)
    # header: lines on the first data row's page, above it, below any earlier paragraph (a gap of > 3 lines' height)
    pg, y_first, _ = lines[first]
    head = [l for l in lines[:first] if l[0] == pg and not amounts_of(l[2])]
    head.reverse()
    chosen, last_y = [], y_first
    for l in head:
        if last_y - l[1] > 40 or len(chosen) >= 6:
            break
        if any(len(t[2]) > 45 for t in l[2]):
            break
        chosen.append(l)
        last_y = l[1]
    chosen.reverse()
    words, name_words = [[] for _ in rights], []
    for _, _, toks in chosen:
        for x0, x1, t in toks:
            if x1 < first_amount_x - 2:
                name_words.append(t)
                continue
            c = (x0 + x1) / 2
            k = min(range(len(rights)), key=lambda q: abs(centres[q] - c))
            if abs(centres[k] - c) <= 45:
                words[k].append(t)
    labels = [" ".join(w).strip() for w in words]
    grid = [[" ".join(name_words).strip() or "Councillor"] + labels]
    for i in data:
        toks = lines[i][2]
        name = " ".join(t[2] for t in toks if t[1] < first_amount_x - 2 and not is_amount(t[2]))
        row = [name] + [""] * len(rights)
        for x0, x1, t in amounts_of(toks):
            k = min(range(len(rights)), key=lambda q: abs(rights[q] - x1))
            row[k + 1] = t
        grid.append(row)
    return [grid]


TOKEN_RE = re.compile(r"\S+(?: \S+)*")


def grid_from_layout_text(text):
    lines = [l.rstrip() for l in text.replace("\f", "\n").split("\n")]
    def tokens(line):
        return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+(?: \S+)*", line)]
    def amounts_of(line):
        return [t for t in tokens(line) if is_amount(t[2])]
    data_idx = [i for i, l in enumerate(lines) if len(amounts_of(l)) >= 2 and re.match(r"\s*[A-Za-z]", l)]
    if not data_idx:
        return []
    # column right edges, clustered
    ends = sorted(t[1] for i in data_idx for t in amounts_of(lines[i]))
    cols = []
    for e in ends:
        if cols and e - cols[-1][-1] <= 3:
            cols[-1].append(e)
        else:
            cols.append([e])
    cols = [c for c in cols if len(c) >= max(2, len(data_idx) // 10)]
    rights = [max(set(c), key=c.count) for c in cols]
    first_data = min(t[0] for i in data_idx for t in amounts_of(lines[i]))
    # header: the non-empty lines just above the first data row (stopping at a gap of two blank lines)
    def header_for(start):
        out, j, blank = [], start - 1, 0
        while j >= 0 and len(out) < 6:
            if not lines[j].strip():
                blank += 1
                if blank >= 2 and out:
                    break
            else:
                blank = 0
                if len(amounts_of(lines[j])) >= 2:
                    break
                out.insert(0, lines[j])
            j -= 1
        return out
    head_lines = header_for(data_idx[0])
    centres = []
    for r in rights:
        spans = [(s + e) / 2 for i in data_idx for s, e, t in amounts_of(lines[i]) if abs(e - r) <= 3]
        centres.append(sum(spans) / len(spans))
    words = [[] for _ in rights]
    name_words = []
    for hl in head_lines:
        for s, e, t in tokens(hl):
            if len(t) > 45:
                continue
            if e < first_data - 1:
                name_words.append(t)
                continue
            c = (s + e) / 2
            k = min(range(len(rights)), key=lambda q: abs(centres[q] - c))
            if abs(centres[k] - c) <= 16:
                words[k].append(t)
    labels = [" ".join(w).strip() for w in words]
    name_label = " ".join(name_words).strip() or "Councillor"
    grid = [[name_label] + labels]
    for i in data_idx:
        line = lines[i]
        name = line[:first_data].strip()
        row = [re.sub(r"\s{2,}", " ", name)] + [""] * len(rights)
        for s, e, t in amounts_of(line):
            k = min(range(len(rights)), key=lambda q: abs(rights[q] - e))
            if abs(rights[k] - e) <= 4:
                row[k + 1] = t
        grid.append(row)
    return [grid]


def grids_for(url, content, ctype):
    u = url.lower()
    if content[:4] == b"%PDF":
        return grid_from_pdf(content)
    if content[:2] == b"PK" or u.endswith((".xlsx", ".xls")) or "spreadsheet" in ctype or "excel" in ctype:
        return grid_from_sheet(content)
    text = content.decode("utf-8", "replace")
    if "csv" in ctype or u.endswith(".csv"):
        return [grid_from_csv(text)]
    return grids_from_html(text)


# ---------------------------------------------------------------- grids to councillors

def read_grid(grid, name_col_hint=None):
    """Find the header row (it mentions 'basic'), then read every councillor row under it."""
    nohead = lambda r: not any(is_amount(c) for c in r if c)
    hdr = next((i for i, r in enumerate(grid[:10]) if nohead(r) and any(re.fullmatch(r"(type of )?(payment|allowance|heading|description)( type)?", c.strip(), re.I) for c in r)), None)
    if hdr is None:
        hdr = next((i for i, r in enumerate(grid[:40]) if nohead(r) and any(re.search(r"basic", c, re.I) for c in r)), None)
    if hdr is None:
        hdr = next((i for i, r in enumerate(grid[:40]) if nohead(r) and sum(1 for c in r if re.search(r"allowance|mileage|travel|subsistence|responsib", c, re.I)) >= 2), None)
    if hdr is None:
        return None
    long = read_long(grid, hdr)
    if long:
        return long
    head = [re.sub(r"(?<=[a-z])(?=[A-Z])", " ", re.sub(r"\s+", " ", c)).strip() for c in grid[hdr]]
    # a header split over two rows (e.g. 'Special' / 'Responsibility Allowance') is joined
    if hdr + 1 < len(grid) and not any(is_amount(c) for c in grid[hdr + 1] if c) and sum(1 for c in grid[hdr + 1] if c) >= 2:
        head = [(a + " " + b).strip() for a, b in zip(head, grid[hdr + 1] + [""] * len(head))]
        hdr += 1
    seen = {}
    for j, h in enumerate(head):  # repeated labels ('Total' twice) are kept apart
        if h:
            seen[h] = seen.get(h, 0) + 1
            if seen[h] > 1:
                head[j] = f"{h} ({seen[h]})"
    amount_cols = [j for j, h in enumerate(head) if h and not re.search(r"name|councillor$|^member ?(type|name)$|^members?$|ward|division|party|group|role|position|post|\bref\b|reference|\bid\b|\buri\b|uri$|label$|number|\bno\.?$|code|unit|date|period|year|latest", h, re.I)]
    name_col = name_col_hint if name_col_hint is not None else next(
        (j for j, h in enumerate(head) if re.search(r"name", h, re.I) and not re.search(r"allowance|basic|total", h, re.I)), None)
    if name_col is None:
        name_col = next((j for j, h in enumerate(head) if re.search(r"councillor|member", h, re.I) and not re.search(r"allowance|basic|total|type", h, re.I)), 0)
    # files in the LGA open-data layout hold several years and publications: keep the latest year's latest
    # publication, and councillors only (co-opted members are not councillors)
    lc = next((j for j, h in enumerate(head) if re.fullmatch(r"latest ?data", h, re.I)), None)
    if lc is not None:
        grid = grid[:hdr + 1] + [r for r in grid[hdr + 1:] if len(r) > lc and str(r[lc]).strip().upper() in ("TRUE", "YES", "1")]
    mt = next((j for j, h in enumerate(head) if re.fullmatch(r"member ?type", h, re.I)), None)
    if mt is not None:
        grid = grid[:hdr + 1] + [r for r in grid[hdr + 1:] if len(r) > mt and not re.search(r"co-?opt", str(r[mt]), re.I)]
    yc = next((j for j, h in enumerate(head) if re.fullmatch(r"financial ?year", h, re.I)), None)
    file_year = None
    if yc is not None:
        years = {year_of(str(r[yc])) for r in grid[hdr + 1:] if len(r) > yc and year_of(str(r[yc]))}
        if years:
            file_year = max(years)
            grid = grid[:hdr + 1] + [r for r in grid[hdr + 1:] if len(r) > yc and year_of(str(r[yc])) == file_year]
    extra = {j: h for j, h in enumerate(head) if j != name_col and re.search(r"ward|division|party|group|role|position|post", h, re.I)}
    rows = []
    for r in grid[hdr + 1:]:
        r = r + [""] * (len(head) - len(r))
        name = re.sub(r"\s+", " ", str(r[name_col])).strip()
        if not name or NOT_A_NAME.match(name) or re.match(r"^(total|grand total|sub-?total)\b", name, re.I) or is_amount(name):
            continue
        vals = {head[j]: amount(r[j]) for j in amount_cols if j != name_col and head[j] and is_amount(r[j] or "-") and r[j] != ""}
        if not vals or all(v in (None, 0) for v in vals.values()) and not any(str(r[j]).strip() for j in amount_cols):
            continue
        if not any(is_amount(r[j]) for j in amount_cols if j != name_col and r[j]):
            continue
        rec = dict(name=name, amounts={k: round(v, 2) for k, v in vals.items() if v is not None})
        for j, h in extra.items():
            if str(r[j]).strip():
                rec[h.lower()] = str(r[j]).strip()
        rows.append(rec)
    headings = [head[j] for j in amount_cols if j != name_col and head[j]]
    return dict(headings=headings, councillors=rows, year=file_year) if rows else None


def read_long(grid, hdr):
    """'Long' statements list one heading per row: councillor | type of payment | amount (the name is often left
    blank on the councillor's later rows).  They are turned into one row per councillor."""
    head = [c.strip().lower() for c in grid[hdr]]
    if sum(1 for h in head if h) > 5:
        return None
    ti = next((j for j, h in enumerate(head) if re.search(r"type|payment|heading|description", h) and not re.search(r"amount|£|total", h)), None)
    ai = next((j for j, h in enumerate(head) if re.search(r"amount|£|value|paid|total", h)), None)
    ni = next((j for j, h in enumerate(head) if re.search(r"councillor|name|member", h)), None)
    if ti is None or ai is None or ni is None or len({ti, ai, ni}) < 3:
        return None
    people, order, cur = {}, [], None
    for r in grid[hdr + 1:]:
        r = r + [""] * (len(head) - len(r))
        name = re.sub(r"\s+", " ", r[ni]).strip()
        if name and not NOT_A_NAME.match(name) and not re.match(r"^(total|grand total)", name, re.I):
            cur = name
        elif name:
            cur = None
            continue
        if not cur or not r[ti].strip() or not is_amount(r[ai]):
            continue
        if cur not in people:
            people[cur] = {}
            order.append(cur)
        h = re.sub(r"\s+", " ", r[ti]).strip()
        people[cur][h] = round(people[cur].get(h, 0) + (amount(r[ai]) or 0), 2)
    if len(order) < 5:
        return None
    headings = []
    for n in order:
        for h in people[n]:
            if h not in headings:
                headings.append(h)
    return dict(headings=headings, councillors=[dict(name=n, amounts=people[n]) for n in order])


def summarise(parsed):
    """Categorise the council's headings, check totals and add each councillor's total."""
    used = {h for c in parsed["councillors"] for h, v in c["amounts"].items() if v}
    heads = [h for h in parsed["headings"] if h in used]  # headings nobody was paid under are left out
    for c in parsed["councillors"]:
        c["amounts"] = {h: v for h, v in c["amounts"].items() if h in used}
    cats = {h: category(h) for h in heads}
    totals = [h for h in heads if cats[h] == "total"]
    # a 'Total' that only adds up allowances (before expenses) is a subtotal; the last total column is the overall one
    overall = totals[-1] if totals else None
    parts = [h for h in heads if cats[h] != "total"]
    bad = []
    for c in parsed["councillors"]:
        s = round(sum(c["amounts"].get(h, 0) for h in parts), 2)
        if overall is not None and overall in c["amounts"]:
            if abs(s - c["amounts"][overall]) > 1.0:
                bad.append(f"{c['name']}: parts {s} vs total {c['amounts'][overall]}")
            c["total"] = c["amounts"][overall]
        else:
            c["total"] = s
    by_cat = {}
    for c in parsed["councillors"]:
        for h in parts:
            by_cat[cats[h]] = round(by_cat.get(cats[h], 0) + c["amounts"].get(h, 0), 2)
    return dict(headings=[dict(label=h, category=cats[h]) for h in heads], councillors=parsed["councillors"], year=parsed.get("year"),
                totals_by_category=by_cat, total=round(sum(c["total"] for c in parsed["councillors"]), 2),
                total_check=dict(column=overall, mismatches=bad[:20], rows_checked=len(parsed["councillors"]) if overall else 0))


def best_parse(grids):
    best = None
    for g in grids:
        p = read_grid(g)
        if p and (best is None or len(p["councillors"]) > len(best["councillors"])):
            best = p
    return best


# ---------------------------------------------------------------- discovery

YEAR_RE = re.compile(r"(?<!\d)(20\d\d)\s*(?:/|-|–|to|_)?\s*(?:20)?(\d\d)(?!\d)")


def year_of(text):
    """'2025-26', '2025/2026', '2025 to 2026', '202526', '1 April 2025 to 31 March 2026' -> '2025-26'."""
    t = text.replace("%20", " ").replace("_", " ")
    for m in YEAR_RE.finditer(t):
        a, b = int(m.group(1)), int(m.group(2))
        if (a + 1) % 100 == b:
            return f"{a}-{b:02d}"
    ys = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", t)]
    for a, b in zip(ys, ys[1:]):
        if b == a + 1:
            return f"{a}-{b % 100:02d}"
    return None


def links(page_url, text):
    out = []
    for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.S):
        out.append((urljoin(page_url, htmllib.unescape(href)), htmllib.unescape(re.sub(r"<[^>]+>|\s+", " ", label)).strip()))
    return out


def discover(src):
    """Return (url, year) of the newest annual statement for a registry entry."""
    if src.get("url"):
        return src["url"], src.get("year")
    page = get(src["landing"])
    pat = re.compile(src["link"], re.I)
    cands = []
    for url, label in links(src["landing"], page.text):
        hay = label + " " + url
        if pat.search(hay) and not re.search(src.get("exclude", r"$^"), hay, re.I):
            y = year_of(label) or year_of(url)
            if y or src.get("undated"):
                cands.append((y or "", url))
    if not cands:
        raise RuntimeError("no annual statement link found on " + src["landing"])
    y, url = max(cands)
    if src.get("follow_link"):  # the link is a page that holds a further download link
        sub = get(url)
        if True:
            p2 = re.compile(src["follow_link"], re.I)
            nxt = next((u for u, l in links(url, sub.text) if p2.search(l + " " + u)), None)
            if not nxt:
                raise RuntimeError("no download link on " + url)
            url = nxt
    return url, y


def import_council(src):
    url, year = discover(src)
    r = get(url)
    grids = grids_for(url, r.content, r.headers.get("content-type", ""))
    parsed = best_parse(grids)
    if not parsed or len(parsed["councillors"]) < src.get("min_councillors", 20):
        raise RuntimeError(f"could not read councillors from {url} ({0 if not parsed else len(parsed['councillors'])} rows)")
    s = summarise(parsed)
    if s["total_check"]["mismatches"]:
        raise RuntimeError(f"{len(s['total_check']['mismatches'])} rows do not add up to their total, e.g. {s['total_check']['mismatches'][0]}")
    year = s.pop("year", None) or year
    if not year:
        raise RuntimeError("could not tell which year the statement covers: " + url)
    return dict(id=src["id"], name=src["name"], type=src["type"], nation=src.get("nation", "England"), year=year,
                source=url, landing=src.get("landing", url), **s)


def main(argv):
    if argv[:1] == ["--grid"]:
        r = get(argv[1])
        for g in grids_for(argv[1], r.content, r.headers.get("content-type", "")):
            print("=== GRID", len(g), "rows")
            for row in g[:200]:
                print(" | ".join(row))
            p = read_grid(g)
            if p:
                s = summarise(p)
                print("PARSED", len(s["councillors"]), "councillors; headings", json.dumps(s["headings"]), "total", s["total"], "check", json.dumps(s["total_check"])[:400])
        return 0
    reg = json.loads(REGISTRY.read_text())
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    report = json.loads(REPORT.read_text()) if REPORT.exists() else {}
    prev = {c["id"]: c for c in out.get("councils", [])}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    only = set(argv)
    for src in reg["councils"]:
        if only and src["id"] not in only:
            continue
        try:
            c = import_council(src)
            c["checked_at"] = now
            prev[src["id"]] = c
            report[src["id"]] = dict(status="updated", checked_at=now, year=c["year"], councillors=len(c["councillors"]), source=c["source"])
        except Exception as exc:
            report[src["id"]] = dict(report.get(src["id"], {}), status="failed_kept_previous", checked_at=now, error=str(exc)[:400])
        print(src["id"], report[src["id"]]["status"], report[src["id"]].get("year", ""), report[src["id"]].get("councillors", ""), report[src["id"]].get("error", ""), flush=True)
    order = {s["id"]: i for i, s in enumerate(reg["councils"])}
    councils = sorted((c for c in prev.values() if c["id"] in order), key=lambda c: order[c["id"]])
    missing = [dict(name=s["name"], reason="its latest statement could not be read automatically yet (" + report.get(s["id"], {}).get("error", "unknown error")[:120] + ").",
                    source=s.get("landing") or s.get("url")) for s in reg["councils"] if s["id"] not in prev]
    payload = dict(retrieved_at=now, councils=councils, frameworks=reg.get("frameworks", []), not_covered=reg.get("not_covered", []) + missing,
                   legal_basis=reg.get("legal_basis"))
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return 0 if councils else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
