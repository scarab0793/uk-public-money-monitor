"""Incremental importer for UK public procurement notices (OCDS).

Sources
  * Contracts Finder  - /Published/Notices/OCDS/Search  (publishedFrom/publishedTo)
  * Find a Tender     - /api/1.0/ocdsReleasePackages     (updatedFrom/updatedTo)

The importer works one UTC day at a time.  Every release is stored unaltered
in the raw archive (see procurement_store.py), partitioned by source and the
month of the release date.  Nothing is ever deleted: a day that fails keeps
whatever was archived before, and the day is retried by the next run.

Modes
  daily     re-fetch the last few complete days (late publications and
            corrections) plus today so far
  backfill  fetch missing days, newest first, back to the source floor,
            until the time budget is spent

State and per-day coverage are kept in data/procurement/import-state.json;
a log of recent runs is kept in data/procurement/import-log.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import procurement_store as store_mod  # noqa: E402

DATA = Path("data/procurement")
STATE_PATH = DATA / "import-state.json"
LOG_PATH = DATA / "import-log.json"

SOURCES = {
    "contracts-finder": {
        "label": "Contracts Finder",
        "url": "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search",
        "from": "publishedFrom",
        "to": "publishedTo",
        "suffix": "Z",
        # Contracts Finder notices are available from 2015; backfill starts here and can be lowered.
        "floor": "2019-01-01",
        "window_basis": "publication date",
    },
    "find-a-tender": {
        "label": "Find a Tender",
        "url": "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages",
        "from": "updatedFrom",
        "to": "updatedTo",
        "suffix": "",
        # Find a Tender replaced OJEU/TED for UK notices on 1 January 2021.
        "floor": "2021-01-01",
        "window_basis": "last-updated date",
    },
}
PAGE_LIMIT = 100
MAX_PAGES_PER_DAY = 3000
REQUEST_PAUSE = 2.0
DAILY_OVERLAP_DAYS = 3


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


class SourceError(RuntimeError):
    pass


class Fetcher:
    def __init__(self, session=None, pause=REQUEST_PAUSE, sleep=time.sleep):
        if session is None:
            import requests
            session = requests.Session()
            session.headers["User-Agent"] = "uk-public-money-monitor/1.0 (+https://github.com/scarab0793/uk-public-money-monitor)"
        self.session = session
        self.pause = pause
        self.sleep = sleep
        self.requests = 0

    def get(self, url, params):
        last = None
        for attempt in range(6):
            try:
                r = self.session.get(url, params=params, timeout=120)
            except Exception as exc:  # network error: back off and retry
                last = repr(exc)
                self.sleep(min(30 * 2 ** attempt, 600))
                continue
            self.requests += 1
            if r.status_code in (403, 429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                wait = r.headers.get("Retry-After", "")
                self.sleep(int(wait) if wait.isdigit() else min(60 * 2 ** attempt, 900))
                continue
            if r.status_code != 200:
                raise SourceError(f"HTTP {r.status_code} for {r.url}")
            try:
                return r.json()
            except ValueError as exc:
                last = f"invalid JSON: {exc}"
                self.sleep(30)
        raise SourceError(f"Gave up after retries ({last}) for {url}")

    def fetch_window(self, source: str, start: dt.datetime, end: dt.datetime):
        cfg = SOURCES[source]
        url = cfg["url"]
        params = {
            cfg["from"]: iso(start).removesuffix("Z") + cfg["suffix"],
            cfg["to"]: iso(end).removesuffix("Z") + cfg["suffix"],
            "limit": PAGE_LIMIT,
        }
        seen, pages, releases, packages = set(), 0, [], []
        host = urlparse(url).hostname
        while url:
            key = (url, json.dumps(params, sort_keys=True))
            if key in seen:
                raise SourceError("Pagination loop detected")
            seen.add(key)
            package = self.get(url, params)
            pages += 1
            if pages > MAX_PAGES_PER_DAY:
                raise SourceError("Too many pages for one day; window not trusted")
            if "releases" not in package or not isinstance(package["releases"], list):
                raise SourceError("Response is not an OCDS release package")
            meta = {k: package.get(k) for k in ("uri", "publishedDate", "publisher", "license", "publicationPolicy", "version") if package.get(k) is not None}
            for rel in package["releases"]:
                releases.append((meta, rel))
            nxt = (package.get("links") or {}).get("next")
            if nxt:
                nxt = urljoin(url, nxt)
                if urlparse(nxt).hostname != host:
                    raise SourceError("Unexpected pagination host")
                if not package["releases"]:
                    raise SourceError("Empty page with a next link")
            url, params = nxt, None
            if url:
                self.sleep(self.pause)
        return releases, pages


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def empty_state():
    return {"schema": 1, "sources": {s: {"days": {}} for s in SOURCES}}


def valid_release(rel) -> str | None:
    if not isinstance(rel, dict):
        return "not an object"
    for f in ("ocid", "id", "date"):
        if not rel.get(f) or not isinstance(rel.get(f), str):
            return f"missing {f}"
    try:
        dt.datetime.fromisoformat(rel["date"].replace("Z", "+00:00"))
    except ValueError:
        return "unparseable date"
    return None


class Importer:
    def __init__(self, store, fetcher, state, today=None, clock=time.monotonic):
        self.store = store
        self.fetcher = fetcher
        self.state = state
        self.today = today or utcnow().date()
        self.clock = clock
        self.pending = defaultdict(dict)  # (source, month) -> {(ocid,id): row}
        self.report = {}

    def source_report(self, source):
        return self.report.setdefault(source, dict(days_complete=0, days_partial=0, days_failed=0, pages=0, releases_fetched=0,
                                                   new=0, changed=0, unchanged=0, quarantined=0, errors=[]))

    def fetch_day(self, source: str, day: dt.date):
        rep = self.source_report(source)
        start = dt.datetime.combine(day, dt.time(), dt.timezone.utc)
        end = start + dt.timedelta(days=1)
        partial = day >= self.today
        if partial:
            end = min(end, utcnow().replace(microsecond=0))
        fetched_at = iso(utcnow())
        try:
            releases, pages = self.fetcher.fetch_window(source, start, end)
        except Exception as exc:
            rep["days_failed"] += 1
            rep["errors"].append(f"{day}: {exc}")
            entry = self.state["sources"][source]["days"].setdefault(str(day), {})
            # A day that was already archived completely stays complete; the refresh error is recorded.
            if entry.get("status") != "complete":
                entry["status"] = "failed"
            entry.update(attempted_at=fetched_at, error=str(exc)[:300])
            return False
        for meta, rel in releases:
            problem = valid_release(rel)
            month = "quarantine" if problem else rel["date"][:7]
            if problem:
                rep["quarantined"] += 1
            key = (str(rel.get("ocid")), str(rel.get("id")), problem or "")
            self.pending[(source, month)][key] = {"source": source, "partition_day": str(day), "fetched_at": fetched_at,
                                                 "package": meta, "release": rel, **({"problem": problem} if problem else {})}
        rep["pages"] += pages
        rep["releases_fetched"] += len(releases)
        rep["days_partial" if partial else "days_complete"] += 1
        self.state["sources"][source]["days"][str(day)] = dict(status="partial" if partial else "complete", releases=len(releases), pages=pages,
                                                                fetched_at=fetched_at, window_end=iso(end))
        return True

    def flush(self):
        """Merge pending releases into partitions and publish changed partitions."""
        changed_paths = []
        for (source, month), new_rows in sorted(self.pending.items()):
            rep = self.source_report(source)
            path = self.store.path(source, month)
            before = store_mod.sha256(path) if path.exists() else None
            rows = {}
            for r in store_mod.read_partition(path) or []:
                rel = r["release"]
                rows[(str(rel.get("ocid")), str(rel.get("id")), r.get("problem", ""))] = r
            for key, r in new_rows.items():
                old = rows.get(key)
                if old is None:
                    rep["new"] += 1
                    rows[key] = r
                elif old["release"] != r["release"]:
                    rep["changed"] += 1
                    r.setdefault("previous_fetched_at", old.get("fetched_at"))
                    rows[key] = r
                else:
                    rep["unchanged"] += 1
            store_mod.write_partition(path, rows.values())
            if store_mod.sha256(path) != before:
                changed_paths.append(path)
        self.pending.clear()
        self.store.publish(changed_paths)
        return changed_paths

    def daily_days(self, source):
        days = self.state["sources"][source]["days"]
        complete = sorted(d for d, v in days.items() if v.get("status") == "complete")
        if complete:
            start = min(dt.date.fromisoformat(complete[-1]) + dt.timedelta(days=1), self.today) - dt.timedelta(days=DAILY_OVERLAP_DAYS)
        else:
            start = self.today - dt.timedelta(days=7)
        # Also retry recent failures and partial days.
        retry = [dt.date.fromisoformat(d) for d, v in days.items() if v.get("status") in ("failed", "partial") and dt.date.fromisoformat(d) >= self.today - dt.timedelta(days=30)]
        out = {start + dt.timedelta(days=i) for i in range((self.today - start).days + 1)} | set(retry)
        return sorted(out)

    def backfill_days(self, source):
        days = self.state["sources"][source]["days"]
        floor = dt.date.fromisoformat(SOURCES[source]["floor"])
        day = self.today - dt.timedelta(days=1)
        while day >= floor:
            if days.get(str(day), {}).get("status") != "complete":
                yield day
            day -= dt.timedelta(days=1)

    def run(self, mode, sources, budget_seconds, checkpoint_seconds=900, on_checkpoint=None):
        started = self.clock()
        last_checkpoint = started
        for source in sources:
            self.source_report(source)
        if mode == "daily":
            for source in sources:
                for day in self.daily_days(source):
                    self.fetch_day(source, day)
            self.flush()
            if on_checkpoint:
                on_checkpoint()
            return self.report
        # Backfill: alternate sources so both progress within one budget.
        iters = {s: iter(self.backfill_days(s)) for s in sources}
        consecutive_failures = defaultdict(int)
        while iters and self.clock() - started < budget_seconds:
            for source in list(iters):
                day = next(iters[source], None)
                if day is None:
                    del iters[source]
                    continue
                ok = self.fetch_day(source, day)
                consecutive_failures[source] = 0 if ok else consecutive_failures[source] + 1
                if consecutive_failures[source] >= 5:
                    self.source_report(source)["errors"].append("Stopped after 5 consecutive failed days")
                    del iters[source]
            if self.clock() - last_checkpoint > checkpoint_seconds:
                self.flush()
                if on_checkpoint:
                    on_checkpoint()
                last_checkpoint = self.clock()
        self.flush()
        if on_checkpoint:
            on_checkpoint()
        return self.report


def coverage_summary(state):
    out = {}
    for source, s in state["sources"].items():
        days = s["days"]
        complete = sorted(d for d, v in days.items() if v.get("status") == "complete")
        out[source] = dict(
            label=SOURCES[source]["label"], endpoint=SOURCES[source]["url"], window_basis=SOURCES[source]["window_basis"],
            floor=SOURCES[source]["floor"], complete_days=len(complete), earliest_complete=complete[0] if complete else None,
            latest_complete=complete[-1] if complete else None,
            failed_days=sorted(d for d, v in days.items() if v.get("status") == "failed"),
            partial_days=sorted(d for d, v in days.items() if v.get("status") == "partial"),
            releases_listed=sum(v.get("releases", 0) for v in days.values() if v.get("status") in ("complete", "partial")),
        )
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("daily", "backfill"), default="daily")
    ap.add_argument("--sources", default=",".join(SOURCES))
    ap.add_argument("--budget-minutes", type=float, default=90)
    ap.add_argument("--raw-dir", default="raw-procurement")
    ap.add_argument("--commit-cmd", default="", help="shell command run after each checkpoint (e.g. git commit/push)")
    args = ap.parse_args(argv)
    sources = [s for s in args.sources.split(",") if s]
    for s in sources:
        if s not in SOURCES:
            ap.error("unknown source " + s)
    state = load_json(STATE_PATH, empty_state())
    for s in SOURCES:
        state["sources"].setdefault(s, {"days": {}})
    store = store_mod.open_store(Path(args.raw_dir))
    importer = Importer(store, Fetcher(), state)
    run_started = iso(utcnow())

    def checkpoint():
        state["coverage"] = coverage_summary(state)
        state["updated_at"] = iso(utcnow())
        save_json(STATE_PATH, state)
        if args.commit_cmd:
            import subprocess
            subprocess.run(args.commit_cmd, shell=True, check=False)

    report = importer.run(args.mode, sources, args.budget_minutes * 60, on_checkpoint=checkpoint)
    log = load_json(LOG_PATH, [])
    log.insert(0, dict(mode=args.mode, started_at=run_started, finished_at=iso(utcnow()), requests=importer.fetcher.requests, sources=report))
    save_json(LOG_PATH, log[:60])
    checkpoint()
    print(json.dumps(report, indent=1))
    complete = sum(r["days_complete"] + r["days_partial"] for r in report.values())
    if complete == 0:
        print("No day was imported successfully", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
