"""Build the published procurement database from the raw OCDS archive.

Input:  raw partitions written by import_procurement.py
Output: data/procurement/ (written to a staging directory first, validated,
        then swapped in, so a failed build never replaces working data)

  summary.json                 coverage, totals, data-quality report
  notices/YYYY-MM.json         one row per procurement process (source + OCID),
                               sharded by month first published
  suppliers/index.json         suppliers with a published registered identifier
  suppliers/detail/XX.json     supplier records, bucketed by key hash
  buyers/index.json, buyers/detail/XX.json

Accounting rules applied here
  * Releases of one OCID are compiled into one process; tender, award and
    contract values are kept as different amount types and never added up.
  * Award and contract values are not payments.  Framework agreements
    (maximum values) are excluded from award totals and reported separately.
  * Suppliers are linked only through published identifiers (Companies House,
    PPON, Charity Commission, ...); suppliers with only a name are not merged.
  * Non-GBP, non-positive and implausibly large values are kept but excluded
    from totals and flagged.
  * The two sources overlap; totals are reported per source, and likely
    cross-source duplicates are flagged rather than removed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import procurement_store as store_mod  # noqa: E402
from import_procurement import SOURCES, STATE_PATH, LOG_PATH, load_json  # noqa: E402

OUT = Path("data/procurement")
SRC_SHORT = {"contracts-finder": "cf", "find-a-tender": "fts"}
NOTICE_URL = {
    "contracts-finder": "https://www.contractsfinder.service.gov.uk/Notice/",
    "find-a-tender": "https://www.find-tender.service.gov.uk/Notice/",
}
DESC_CHARS = 300
IMPLAUSIBLE_GBP = 50_000_000_000  # single award above £50bn is flagged for review
# Identifier schemes that name a legal entity in a public register.
REGISTERED_SCHEMES = ("GB-COH", "GB-PPON", "GB-CHC", "GB-SC", "GB-NIC", "GB-MPR", "GB-EDU", "GB-NHS", "GB-UKPRN", "GB-GOR", "GB-LAE", "GB-LAS", "GB-PLA", "GB-SHPE", "GB-UKCRN")
# Source-local supplier registrations: stable inside one portal only.
LOCAL_SCHEMES = ("GB-CFS", "GB-FTS", "GB-SRS")
SCHEME_RANK = {s: i for i, s in enumerate(REGISTERED_SCHEMES + LOCAL_SCHEMES)}


def norm_space(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def norm_key(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def split_identifier(raw):
    """'GB-COH-02036219' -> ('GB-COH', '02036219'); returns None for junk."""
    raw = norm_space(raw).upper()
    for scheme in sorted(SCHEME_RANK, key=len, reverse=True):
        if raw.startswith(scheme + "-"):
            return clean_identifier(scheme, raw[len(scheme) + 1:])
    return None


def clean_identifier(scheme, ident):
    scheme = norm_space(scheme).upper()
    ident = re.sub(r"\s+", "", str(ident or "")).upper()
    if scheme not in SCHEME_RANK or not ident:
        return None
    if scheme == "GB-COH":
        if ident.isdigit():
            ident = ident.zfill(8)
        if not re.fullmatch(r"[A-Z0-9]{8}", ident) or ident.strip("0") == "":
            return None
    elif len(re.sub(r"[^A-Z0-9]", "", ident)) < 3 or re.fullmatch(r"0+|N/?A|NONE|NULL|UNKNOWN", ident):
        return None
    return scheme, ident


def party_identifiers(party):
    ids = set()
    for ident in [party.get("identifier")] + list(party.get("additionalIdentifiers") or []):
        if isinstance(ident, dict) and ident.get("id"):
            c = clean_identifier(ident.get("scheme"), ident.get("id"))
            if c:
                ids.add(c)
    if party.get("id"):
        c = split_identifier(party["id"])
        if c:
            ids.add(c)
    return ids


def money(v):
    if not isinstance(v, dict):
        return None
    amt = v.get("amount")
    if amt is None:
        return None
    try:
        amt = float(amt)
    except (TypeError, ValueError):
        return None
    return [round(amt, 2), (v.get("currency") or "").upper() or None]


def merge_by_id(old: dict, items, fold):
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("id", f"#{i}"))
        old[key] = fold(old.get(key, {}), item)


def framework_kind(tender):
    details = norm_key(tender.get("procurementMethodDetails"))
    if any(k in details for k in ("call off", "mini competition", "under framework", "under a framework", "dynamic purchasing")):
        return "call_off"
    techs = [tender.get("techniques") or {}] + [(lot or {}).get("techniques") or {} for lot in tender.get("lots") or [] if isinstance(lot, dict)]
    for tech in techs:
        if tech.get("hasFrameworkAgreement") is True or tech.get("frameworkAgreement"):
            return "framework"
    if tender.get("hasFrameworkAgreement") is True or "framework" in details:
        return "framework"
    return None


class Process:
    __slots__ = ("source", "ocid", "title", "desc", "buyer", "tags", "status", "first", "last", "n", "amend", "tender_value",
                 "fw", "cat", "cpv", "regions", "urls", "awards", "contracts", "parties", "release_ids", "tam")

    def __init__(self, source, ocid):
        self.source, self.ocid = source, ocid
        self.title = self.desc = self.buyer = self.status = self.first = self.last = self.tender_value = self.fw = self.cat = self.cpv = None
        self.tags, self.regions, self.urls, self.release_ids = [], set(), [], set()
        self.n = self.amend = self.tam = 0
        self.awards, self.contracts, self.parties = {}, {}, {}

    def add(self, rel):
        rid = str(rel.get("id"))
        if rid in self.release_ids:
            return
        self.release_ids.add(rid)
        self.n += 1
        date = rel.get("date")
        newer = self.last is None or (date or "") >= self.last
        self.first = min(filter(None, [self.first, date]), default=None)
        self.last = max(filter(None, [self.last, date]), default=None)
        tags = rel.get("tag") or []
        if newer:
            self.tags = list(tags)
        self.amend += sum(1 for t in tags if "amendment" in str(t).lower())
        tender = rel.get("tender") or {}
        self.tam = max(self.tam, len(tender.get("amendments") or []))
        if newer or self.title is None:
            title = norm_space(tender.get("title") or (rel.get("planning") or {}).get("project"))
            if title:
                self.title = title
            desc = norm_space(tender.get("description"))
            if desc:
                self.desc = desc[:DESC_CHARS] + ("…" if len(desc) > DESC_CHARS else "")
            if tender.get("status"):
                self.status = tender.get("status")
            tv = money(tender.get("value"))
            if tv:
                self.tender_value = tv
            fw = framework_kind(tender)
            if fw:
                self.fw = fw
            if tender.get("mainProcurementCategory"):
                self.cat = tender.get("mainProcurementCategory")
            cls = tender.get("classification") or {}
            if cls.get("id"):
                self.cpv = str(cls["id"])
        for item in (tender.get("items") or []):
            if not self.cpv:
                cls = item.get("classification") or next(iter(item.get("additionalClassifications") or []), {})
                if cls.get("scheme", "CPV") == "CPV" and cls.get("id"):
                    self.cpv = str(cls["id"])
            for addr in item.get("deliveryAddresses") or ([item["deliveryAddress"]] if item.get("deliveryAddress") else []):
                if isinstance(addr, dict) and addr.get("region"):
                    self.regions.add(str(addr["region"])[:40])
        buyer = rel.get("buyer") or {}
        if buyer.get("name") and (newer or not self.buyer):
            self.buyer = {"id": buyer.get("id"), "name": norm_space(buyer["name"])}
        merge_by_id(self.parties, rel.get("parties"), lambda o, p: {"name": norm_space(p.get("name")) or o.get("name"),
                                                                       "ids": sorted(set(map(tuple, o.get("ids", []))) | party_identifiers(p)),
                                                                       "roles": sorted(set(o.get("roles", [])) | set(p.get("roles") or []))})

        def fold_award(o, a):
            o = dict(o)
            if a.get("date"):
                o["date"] = a["date"]
            if a.get("status"):
                o["status"] = a["status"]
            v = money(a.get("value"))
            if v:
                o["value"] = v
            if a.get("suppliers"):
                o["suppliers"] = [[s.get("id"), norm_space(s.get("name"))] for s in a["suppliers"] if isinstance(s, dict)]
            if a.get("title") and not o.get("title"):
                o["title"] = norm_space(a["title"])
            for item in a.get("items") or []:
                for addr in item.get("deliveryAddresses") or []:
                    if isinstance(addr, dict) and addr.get("region"):
                        self.regions.add(str(addr["region"])[:40])
            if not self.cat and a.get("mainProcurementCategory"):
                self.cat = a["mainProcurementCategory"]
            for d in a.get("documents") or []:
                self._url(d.get("url"))
            return o

        def fold_contract(o, c):
            o = dict(o)
            for k in ("awardID", "status", "dateSigned"):
                if c.get(k):
                    o[k] = c[k]
            v = money(c.get("value"))
            if v:
                o["value"] = v
            period = c.get("period") or {}
            if period.get("startDate"):
                o["start"] = period["startDate"][:10]
            if period.get("endDate"):
                o["end"] = period["endDate"][:10]
            o["amendments"] = max(o.get("amendments", 0), len(c.get("amendments") or []))
            for d in c.get("documents") or []:
                self._url(d.get("url"))
            return o

        merge_by_id(self.awards, rel.get("awards"), fold_award)
        merge_by_id(self.contracts, rel.get("contracts"), fold_contract)
        for d in tender.get("documents") or []:
            self._url(d.get("url"))
        if self.source == "find-a-tender":
            self._url(NOTICE_URL[self.source] + rid)

    def _url(self, url):
        if isinstance(url, str) and "/Notice/" in url and "Attachment" not in url and url.startswith(tuple(NOTICE_URL.values())):
            url = url.split("?")[0]
            if url not in self.urls and len(self.urls) < 12:
                self.urls.append(url)

    def source_url(self):
        if self.urls:
            return self.urls[-1] if self.source == "find-a-tender" else self.urls[0]
        if self.source == "contracts-finder":
            m = re.match(r"ocds-b5fd17-(.+)$", self.ocid)
            if m:
                return NOTICE_URL[self.source] + m.group(1)
        return None


def stage_of(p: Process):
    tags = set(p.tags)
    if p.status in ("cancelled", "unsuccessful") or any("Cancellation" in t for t in tags):
        return "cancelled"
    if any(t.startswith("contractTermination") for t in tags):
        return "terminated"
    if p.contracts:
        return "contract"
    if p.awards:
        return "award"
    if any(t.startswith("tender") for t in tags) or p.status in ("active", "complete"):
        return "tender"
    if any(t.startswith("planning") for t in tags):
        return "planning"
    return "other"


class UnionFind:
    def __init__(self):
        self.parent, self.coh = {}, {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def add(self, x):
        r = self.find(x)
        if x[0] == "GB-COH":
            self.coh.setdefault(r, x)

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        ca, cb = self.coh.get(ra), self.coh.get(rb)
        if ca and cb and ca != cb:
            return False  # never merge two different Companies House numbers
        self.parent[rb] = ra
        if cb and not ca:
            self.coh[ra] = cb
        return True


def supplier_key(ident):
    return f"{ident[0]}-{ident[1]}"


def bucket(key):
    return hashlib.sha1(key.encode()).hexdigest()[:2]


def gbp_for_total(value, fw):
    """Return an amount that may be summed as an award value, or None."""
    if not value or value[1] != "GBP" or fw == "framework":
        return None
    if value[0] <= 0 or value[0] > IMPLAUSIBLE_GBP:
        return None
    return value[0]


def build(raw_dir: Path, out_dir: Path, generated_at=None):
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store = store_mod.LocalStore(raw_dir)
    procs: dict[tuple, Process] = {}
    quality = defaultdict(Counter)
    partitions = []
    for source, month, path in store.partitions():
        if source not in SOURCES:
            continue
        n = 0
        for row in store_mod.read_partition(path):
            n += 1
            if month == "quarantine" or row.get("problem"):
                quality[source]["quarantined_releases"] += 1
                continue
            rel = row["release"]
            key = (source, rel["ocid"])
            p = procs.get(key)
            if p is None:
                p = procs[key] = Process(source, rel["ocid"])
            p.add(rel)
            quality[source]["releases"] += 1
        partitions.append(dict(source=source, month=month, releases=n, bytes=path.stat().st_size, sha256=store_mod.sha256(path)))

    # ---- suppliers: identifier graph -------------------------------------------------
    uf = UnionFind()
    conflicts = 0
    for p in procs.values():
        for party in p.parties.values():
            ids = [tuple(i) for i in party.get("ids", [])]
            for i in ids:
                uf.add(i)
            for i in ids[1:]:
                if not uf.union(ids[0], i):
                    conflicts += 1

    def resolve_supplier(p, sid, name):
        party = p.parties.get(str(sid)) if sid else None
        ids = [tuple(i) for i in party.get("ids", [])] if party else []
        if not ids and sid:
            c = split_identifier(sid)
            if c:
                ids = [c]
                uf.add(c)
        if not ids:
            return None
        return uf.find(ids[0])

    comp_ids = defaultdict(set)
    for x in list(uf.parent):
        comp_ids[uf.find(x)].add(x)

    def canonical(root):
        ids = comp_ids.get(root) or {root}
        return min(ids, key=lambda i: (SCHEME_RANK.get(i[0], 99), i[1]))

    suppliers = {}
    buyers = {}
    month_rows = defaultdict(list)
    totals = defaultdict(lambda: defaultdict(lambda: dict(notices=0, awards=0, award_value_gbp=0.0, awards_valued=0, framework_awards=0, framework_value_gbp=0.0)))
    stage_counts = defaultdict(Counter)
    largest = []
    dup_index = defaultdict(list)

    for (source, ocid), p in procs.items():
        q = []
        if not p.title:
            q.append("no_title")
            quality[source]["no_title"] += 1
        if not p.buyer:
            q.append("no_buyer")
            quality[source]["no_buyer"] += 1
        stage = stage_of(p)
        stage_counts[source][stage] += 1
        month = (p.first or "0000-00")[:7]
        year = month[:4]
        nid = f"{SRC_SHORT[source]}:{ocid}"
        # buyer key
        bname = (p.buyer or {}).get("name")
        bparty = p.parties.get(str((p.buyer or {}).get("id"))) if p.buyer else None
        bids = sorted((tuple(i) for i in (bparty or {}).get("ids", []) if tuple(i)[0] in REGISTERED_SCHEMES), key=lambda i: SCHEME_RANK[i[0]])
        bkey = supplier_key(bids[0]) if bids else ("name:" + norm_key(bname) if bname else None)
        awards_out = []
        contract_by_award = {}
        for c in p.contracts.values():
            if c.get("awardID"):
                contract_by_award.setdefault(str(c["awardID"]), c)
        for aid, a in sorted(p.awards.items()):
            if a.get("status") in ("cancelled", "unsuccessful"):
                continue
            c = contract_by_award.get(aid) or {}
            cvalue = c.get("value")
            # Awarded value: the award value, or the signed contract value where no award value is published.
            value = a.get("value") or cvalue
            adate = (a.get("date") or c.get("dateSigned") or c.get("start") or "")[:10]
            sup_out = []
            for sid, sname in a.get("suppliers", []):
                root = resolve_supplier(p, sid, sname)
                skey = supplier_key(canonical(root)) if root else None
                sup_out.append([sname or None, skey])
                if skey:
                    s = suppliers.setdefault(skey, dict(names=Counter(), ids=set(), awards=[], buyers=Counter(), total=0.0, valued=0, fw=0))
                    s["names"][sname] += 1
                    s["ids"].update(supplier_key(i) for i in comp_ids.get(root, {root}))
                    s["buyers"][bname] += 1
                    amt = gbp_for_total(value, p.fw)
                    if amt is not None:
                        s["total"] += amt
                        s["valued"] += 1
                    if p.fw == "framework":
                        s["fw"] += 1
                    s["awards"].append([nid, month, p.title, bname, adate, value, p.fw])
            if value and value[1] and value[1] != "GBP":
                quality[source]["non_gbp_awards"] += 1
            if value and value[1] == "GBP" and value[0] > IMPLAUSIBLE_GBP:
                quality[source]["implausible_award_values"] += 1
                q.append("implausible_value")
            if not value:
                quality[source]["awards_without_value"] += 1
            awards_out.append([adate or None, value, cvalue, sup_out, c.get("start"), c.get("end")])
            ayear = (adate or p.first or "")[:4]
            t = totals[source][ayear]
            t["awards"] += 1
            amt = gbp_for_total(value, p.fw)
            if p.fw == "framework":
                t["framework_awards"] += 1
                if value and value[1] == "GBP" and 0 < value[0] <= IMPLAUSIBLE_GBP:
                    t["framework_value_gbp"] += value[0]
            elif amt is not None:
                t["award_value_gbp"] += amt
                t["awards_valued"] += 1
                largest.append((amt, nid, month, p.title, bname, adate, [s[0] for s in sup_out], source))
            if value:
                dup_index[(norm_key(p.title), norm_key(bname), value[0])].append(nid)
        totals[source][year]["notices"] += 1
        if bkey:
            b = buyers.setdefault(bkey, dict(names=Counter(), notices=[], awards=0, total=0.0))
            b["names"][bname] += 1
            b["notices"].append([nid, month, p.title, stage, (p.first or "")[:10], p.tender_value])
            b["awards"] += len(awards_out)
            b["total"] += sum(gbp_for_total(a[1], p.fw) or 0 for a in awards_out)
        amendments = max(p.amend, p.tam) + sum(c.get("amendments", 0) for c in p.contracts.values())
        row = dict(id=nid, src=SRC_SHORT[source], ocid=ocid, t=p.title, d=p.desc, b=bname, bk=bkey, st=stage, s=p.status,
                   fp=(p.first or "")[:10] or None, lu=(p.last or "")[:10] or None, v=p.tender_value, fw=p.fw, cat=p.cat, cpv=p.cpv,
                   reg=sorted(p.regions)[:6] or None, url=p.source_url(), aw=awards_out or None, n=p.n, am=amendments or None,
                   q=q or None)
        month_rows[month].append({k: v for k, v in row.items() if v is not None})

    # cross-source duplicate flags (never removed)
    dup_pairs = 0
    by_id = {}
    for rows in month_rows.values():
        for r in rows:
            by_id[r["id"]] = r
    for ids in dup_index.values():
        srcs = {i.split(":")[0] for i in ids}
        if len(srcs) > 1:
            fts = [i for i in ids if i.startswith("fts:")]
            for i in ids:
                if i.startswith("cf:") and fts:
                    by_id[i]["dup"] = fts[0]
                    dup_pairs += 1

    # ---- write -----------------------------------------------------------------------
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "notices").mkdir(parents=True)

    def dump(path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")

    months = []
    for month, rows in sorted(month_rows.items()):
        rows.sort(key=lambda r: (r.get("fp") or "", r["id"]), reverse=True)
        dump(out_dir / "notices" / f"{month}.json", dict(month=month, rows=rows))
        months.append(dict(month=month, notices=len(rows), cf=sum(r["src"] == "cf" for r in rows), fts=sum(r["src"] == "fts" for r in rows)))

    sup_index, sup_buckets = [], defaultdict(dict)
    for key, s in suppliers.items():
        name = s["names"].most_common(1)[0][0]
        last = max((a[4] for a in s["awards"]), default="")
        sup_index.append([key, name, len(s["awards"]), round(s["total"], 2), s["fw"], last])
        s["awards"].sort(key=lambda a: a[4], reverse=True)
        sup_buckets[bucket(key)][key] = dict(name=name, names=[n for n, _ in s["names"].most_common(10)], identifiers=sorted(s["ids"]),
                                             award_value_gbp=round(s["total"], 2), awards_valued=s["valued"], framework_awards=s["fw"],
                                             buyers=s["buyers"].most_common(25), awards=s["awards"][:500], awards_total=len(s["awards"]))
    sup_index.sort(key=lambda r: (-r[3], r[1]))
    dump(out_dir / "suppliers" / "index.json", dict(fields=["key", "name", "awards", "award_value_gbp", "framework_awards", "last_award"], rows=sup_index))
    for b, items in sup_buckets.items():
        dump(out_dir / "suppliers" / "detail" / f"{b}.json", items)

    buy_index, buy_buckets = [], defaultdict(dict)
    for key, b in buyers.items():
        name = b["names"].most_common(1)[0][0]
        buy_index.append([key, name, len(b["notices"]), b["awards"], round(b["total"], 2)])
        b["notices"].sort(key=lambda n: n[4], reverse=True)
        buy_buckets[bucket(key)][key] = dict(name=name, names=[n for n, _ in b["names"].most_common(10)], notices=b["notices"][:500],
                                             notices_total=len(b["notices"]), awards=b["awards"], award_value_gbp=round(b["total"], 2))
    buy_index.sort(key=lambda r: (-r[2], r[1]))
    dump(out_dir / "buyers" / "index.json", dict(fields=["key", "name", "notices", "awards", "award_value_gbp"], rows=buy_index))
    for k, items in buy_buckets.items():
        dump(out_dir / "buyers" / "detail" / f"{k}.json", items)

    largest.sort(key=lambda x: -x[0])
    state = load_json(STATE_PATH, {})
    summary = dict(
        generated_at=generated_at,
        basis=("Notices published on Contracts Finder and Find a Tender, compiled per OCDS process (OCID). Tender values are estimates; "
               "award and contract values are not payments. Framework agreement values are maximum call-off capacity and are reported "
               "separately. The two portals overlap, so totals are per source and must not be added together."),
        licence="Contains public sector information licensed under the Open Government Licence v3.0.",
        coverage=state.get("coverage", {}),
        last_runs=load_json(LOG_PATH, [])[:5],
        sources={s: dict(label=SOURCES[s]["label"], endpoint=SOURCES[s]["url"], processes=sum(1 for k in procs if k[0] == s),
                         releases=quality[s]["releases"], stages=dict(stage_counts[s]),
                         by_year={y: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()} for y, t in sorted(totals[s].items())})
                 for s in SOURCES},
        quality={s: dict(quality[s]) for s in SOURCES} | dict(identifier_conflicts=conflicts, possible_cross_source_duplicates=dup_pairs),
        suppliers=dict(identified=len(sup_index), top=sup_index[:25]),
        buyers=dict(total=len(buy_index), top=buy_index[:25]),
        largest_awards=[dict(amount_gbp=a[0], id=a[1], month=a[2], title=a[3], buyer=a[4], date=a[5], suppliers=a[6], source=a[7]) for a in largest[:50]],
        months=months,
        raw_archive=dict(location=f"GitHub release '{store_mod.RAW_RELEASE_TAG}'", partitions=partitions),
    )
    dump(out_dir / "summary.json", summary)
    return summary


def validate(summary, previous):
    total = sum(s["processes"] for s in summary["sources"].values())
    if total == 0:
        raise SystemExit("Build produced no procurement processes; keeping the previous dataset")
    if previous:
        prev_total = sum(s.get("processes", 0) for s in previous.get("sources", {}).values())
        if prev_total and total < prev_total * 0.95:
            raise SystemExit(f"Process count fell from {prev_total} to {total}; keeping the previous dataset")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="raw-procurement")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    staging = out.parent / (out.name + ".staging")
    summary = build(Path(args.raw_dir), staging)
    previous = load_json(out / "summary.json", None)
    validate(summary, previous)
    for name in ("summary.json", "notices", "suppliers", "buyers"):
        target = out / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        shutil.move(str(staging / name), str(target))
    shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps({s: {k: v for k, v in d.items() if k != "by_year"} for s, d in summary["sources"].items()}, indent=1))
    print("quality", json.dumps(summary["quality"]))
    print("suppliers", summary["suppliers"]["identified"], "buyers", summary["buyers"]["total"], "months", len(summary["months"]))


if __name__ == "__main__":
    main()
