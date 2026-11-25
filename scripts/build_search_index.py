"""Build the site-wide search index (data/search/index.json) from the published datasets.

Each entry is a compact array: [name, type, detail, link, amount_gbp_or_null, period]
Links either open a record directly (procurement suppliers/buyers) or use the
'#go/<section>/<input>/<query>' convention, which scrolls to a section and fills its
search box.  Only data already published on the site is indexed.
"""
import json
import os
from pathlib import Path
from urllib.parse import quote

D = Path("data")
OUT = D / "search" / "manifest.json"


def load(path):
    try:
        return json.loads((D / path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def go(section, field, query):
    return f"#go/{section}/{field}/{quote(str(query), safe='')}"


def main():
    items, counts = [], {}

    def add(kind, *entry):
        items.append([entry[0], kind, *entry[1:]])
        counts[kind] = counts.get(kind, 0) + 1

    gm = load("gmpp-2025-26-full-records.json")
    if gm:
        for r in gm["records"]:
            wlc = r.get("whole_life_cost_gbp")
            try:
                wlc = float(wlc) if wlc not in (None, "") else None
            except ValueError:
                wlc = None
            add("Major project", r["project_name"], f"{r.get('department', '')} · {r.get('category', '')} · whole-life cost estimate",
                go("project-detail-2025", "detail2025-search", r["project_name"]), wlc, "2025-26")
    hist = load("gmpp-history.json")
    if hist:
        seen = {i[0].casefold() for i in items}
        for r in hist["records"]:
            if r["name"].casefold() in seen:
                continue
            seen.add(r["name"].casefold())
            add("Major project (historical)", r["name"], f"{r.get('department', '')} · last reported {r.get('year', '')}",
                go("history", "history-search", r["name"]), None, r.get("year"))
    fc = load("fcdo-normalized/index.json")
    if fc:
        for p in fc:
            title = next((t for t in p["titles"] if t), p["activity_id"])
            years = sorted(p["years"])
            total = sum(float(v) for v in p["years"].values())
            add("Overseas aid project", title[:120], f"{p['agency']} · {', '.join(p['countries'][:2])}{' …' if len(p['countries']) > 2 else ''}",
                go("fcdo-projects", "fcdo-query", p["activity_id"]), round(total, 2), f"{years[0]}–{years[-1]}" if years else None)
    sup = load("procurement/suppliers/index.json")
    if sup:
        for key, name, n, total, fw, last in sup["rows"]:
            add("Supplier", name, f"{key} · {n} contract award(s)", f"#procurement/supplier/{quote(key, safe='')}", total or None, last[:4] if last else None)
    buy = load("procurement/buyers/index.json")
    if buy:
        for key, name, n, awards, total in buy["rows"]:
            add("Public buyer", name, f"{n} procurement(s) · {awards} award(s)", f"#procurement/buyer/{quote(key, safe='')}", total or None, None)
    ct = load("local-government/council-tax-england.json")
    if ct:
        for r in ct["area_bills"]["rows"]:
            add("Council", r["Authority"], f"Council Tax {ct['financial_year']} · Band D bill", go("council-tax", "ct-query", r["Authority"]), r.get("Band D"), ct["financial_year"])
    rc = load("hmrc/receipts.json")
    if rc:
        for t in rc["taxes"]:
            last = next((a for a in reversed(t["annual"]) if a[1] is not None), None)
            alias = {"Value Added Tax": " · VAT", "National Insurance Contributions": " · NICs", "Capital Gains Tax": " · CGT", "Inheritance Tax": " · IHT",
                     "Stamp Duty Land Tax": " · SDLT", "Air Passenger Duty": " · APD", "Insurance Premium Tax": " · IPT", "Hydrocarbon Oil (Fuel duties)": " · fuel duty petrol diesel"}.get(t["name"], "")
            add("Tax", t["name"], "HMRC cash receipts" + alias, go("hmrc-receipts", "receipts-filter", t["name"].split(" (")[0]),
                last[1] * 1e6 if last else None, last[0] if last else None)
    cra = load("treasury/country-regional-analysis.json")
    if cra:
        for r in cra["tables"]["A.1a"]["rows"]:
            if r["level"] in ("nation", "english_region"):
                v = r["blocks"][0][-1]
                add("Nation or region", r["area"].replace("Total ", ""), "Identifiable public spending", "#regional-spending", v[2] * 1e6 if v[2] else None, v[0])
    import re
    import shutil
    folder = OUT.parent
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    groups = {}
    for it in items:
        groups.setdefault(it[1], []).append([it[0], it[2], it[3], it[4], it[5]])
    manifest = []
    for kind, rows in groups.items():
        slug = re.sub(r"[^a-z0-9]+", "-", kind.lower()).strip("-")
        details = sorted({r[1] for r in rows})
        di = {d: i for i, d in enumerate(details)}
        prefix = os.path.commonprefix([r[2] for r in rows]) if len(rows) > 1 else ""
        packed = dict(details=details, link_prefix=prefix,
                      rows=[[r[0], di[r[1]], r[2][len(prefix):], r[3], r[4]] for r in rows])
        (folder / f"{slug}.json").write_text(json.dumps(packed, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        manifest.append(dict(type=kind, file=f"{slug}.json", count=len(rows), bytes=(folder / f"{slug}.json").stat().st_size))
    (folder / "manifest.json").write_text(json.dumps(dict(fields=["name", "detail_index", "link_suffix", "amount_gbp", "period"], files=manifest), indent=1), encoding="utf-8")
    print(json.dumps(manifest, indent=1))

if __name__ == "__main__":
    main()
