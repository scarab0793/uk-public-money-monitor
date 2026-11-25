"""Diagnostic: list GOV.UK publication attachments and preview spreadsheet structure.
Usage: python explore_govuk.py <govuk path> [attachment-substring ...]"""
import io, sys, json, requests, pandas as pd
path = sys.argv[1]; full = [a[6:] for a in sys.argv[2:] if a.startswith("sheet=")]
wanted = [w.lower() for w in sys.argv[2:] if not w.startswith("sheet=")]
if path.startswith("search:"):
    q = requests.get("https://www.gov.uk/api/search.json", params={"q": path[7:], "count": 15, "fields": "title,link,public_timestamp,format"}, timeout=60).json()
    for r in q.get("results", []):
        print("HIT", r.get("public_timestamp", "")[:10], r.get("format"), r.get("title"), "|", r.get("link"))
    path = next((r["link"] for r in q.get("results", []) if r.get("link", "").startswith(("/government/statistics/", "/government/publications/"))), None)
    if not path:
        sys.exit(0)
api = "https://www.gov.uk/api/content/" + path.strip("/")
d = requests.get(api, timeout=60).json()
print("TITLE", d.get("title"), "| updated", d.get("public_updated_at"))
docs = d.get("details", {}).get("attachments") or []
for doc in d.get("links", {}).get("documents", []) or []:
    print("DOC", doc.get("base_path"))
for a in docs:
    print("ATT", a.get("title"), "|", a.get("url"), "|", a.get("content_type"))
for a in docs:
    url = a.get("url") or ""
    if not wanted or not any(w in (url + (a.get("title") or "")).lower() for w in wanted):
        continue
    if not url.lower().endswith((".ods", ".xlsx", ".xls", ".csv")):
        continue
    print("=== PREVIEW", url)
    raw = requests.get(url, timeout=180).content
    if url.lower().endswith(".csv"):
        print(raw[:3000].decode("utf-8", "replace")); continue
    book = pd.ExcelFile(io.BytesIO(raw), engine="odf" if url.lower().endswith(".ods") else None)
    for s in book.sheet_names:
        if full and s in full:
            df = book.parse(s, header=None)
            print("--- FULL SHEET", s, df.shape)
            for i in range(len(df)):
                cells = [f"{j}:{str(v)[:90]}" for j, v in enumerate(df.iloc[i].tolist()) if str(v) != "nan"]
                if cells:
                    print("ROW", i, " | ".join(cells)[:4000])
            continue
        if full:
            continue
        df = book.parse(s, header=None, nrows=14)
        print("--- SHEET", s, df.shape)
        print(df.iloc[:14, :12].to_string(max_colwidth=28))
        for i in range(min(len(df), 10)):
            cells = [f"{j}:{str(v)[:70]}" for j, v in enumerate(df.iloc[i].tolist()) if str(v) != "nan"]
            if cells:
                print("ROW", i, " | ".join(cells)[:3000])
