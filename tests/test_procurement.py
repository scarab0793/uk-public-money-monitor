"""Offline tests for the procurement importer and builder; no network access."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_procurement as bp  # noqa: E402
import import_procurement as ip  # noqa: E402
import procurement_store as ps  # noqa: E402


def release(ocid, rid, date, **kw):
    r = {"ocid": ocid, "id": rid, "date": date, "tag": kw.pop("tag", ["tender"])}
    r.update(kw)
    return r


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.headers, self.url = payload, status, {}, "fake"

    def json(self):
        return self.payload


class FakeSession:
    """Serves pages keyed by the requested day; records calls."""

    def __init__(self, pages_by_day, fail_days=()):
        self.pages_by_day, self.fail_days, self.calls = pages_by_day, set(fail_days), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if params:
            day = next(v for k, v in params.items() if k.endswith("From"))[:10]
            self.current = day
            page = 0
        else:
            day, page = self.current, int(url.rsplit("page=", 1)[1])
        if day in self.fail_days:
            return FakeResponse({}, 500)
        pages = self.pages_by_day.get(day, [[]])
        payload = {"releases": pages[page], "publisher": {"name": "test"}, "license": "OGL"}
        if page + 1 < len(pages):
            payload["links"] = {"next": url.split("?")[0] + f"?page={page + 1}"}
        return FakeResponse(payload)


def make_importer(tmp, session, today=dt.date(2026, 11, 25), state=None):
    store = ps.LocalStore(Path(tmp) / "raw")
    fetcher = ip.Fetcher(session=session, pause=0, sleep=lambda s: None)
    return ip.Importer(store, fetcher, state or ip.empty_state(), today=today)


class ImporterTests(unittest.TestCase):
    def test_pagination_partitioning_and_idempotent_merge(self):
        pages = {"2026-11-20": [[release("ocds-b5fd17-a", "r1", "2026-11-20T10:00:00Z")], [release("ocds-b5fd17-b", "r2", "2026-10-31T23:00:00Z")]]}
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, FakeSession(pages))
            self.assertTrue(imp.fetch_day("contracts-finder", dt.date(2026, 11, 20)))
            changed = imp.flush()
            self.assertEqual(len(changed), 2)  # October and November partitions
            months = {m for _, m, _ in imp.store.partitions("contracts-finder")}
            self.assertEqual(months, {"2026-10", "2026-11"})
            self.assertEqual(imp.state["sources"]["contracts-finder"]["days"]["2026-11-20"]["releases"], 2)
            # Second identical fetch: nothing new, nothing re-published.
            imp.fetch_day("contracts-finder", dt.date(2026, 11, 20))
            self.assertEqual(imp.flush(), [])
            self.assertEqual(imp.report["contracts-finder"]["unchanged"], 2)

    def test_changed_release_is_replaced_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, FakeSession({"2026-11-20": [[release("o", "r1", "2026-11-20T10:00:00Z", tender={"title": "A"})]]}))
            imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)); imp.flush()
            imp.fetcher.session = FakeSession({"2026-11-20": [[release("o", "r1", "2026-11-20T10:00:00Z", tender={"title": "B"})]]})
            imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)); imp.flush()
            rows = list(ps.read_partition(imp.store.path("find-a-tender", "2026-11")))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["release"]["tender"]["title"], "B")
            self.assertEqual(imp.report["find-a-tender"]["changed"], 1)

    def test_failed_day_keeps_existing_data_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, FakeSession({"2026-11-20": [[release("o", "r1", "2026-11-20T10:00:00Z")]]}))
            imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)); imp.flush()
            imp.fetcher.session = FakeSession({}, fail_days={"2026-11-20"})
            self.assertFalse(imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)))
            imp.flush()
            self.assertEqual(len(list(ps.read_partition(imp.store.path("find-a-tender", "2026-11")))), 1)
            day = imp.state["sources"]["find-a-tender"]["days"]["2026-11-20"]
            self.assertEqual(day["status"], "complete")
            self.assertIn("error", day)

    def test_invalid_release_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, FakeSession({"2026-11-20": [[{"id": "x", "date": "2026-11-20T00:00:00Z"}]]}))
            imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)); imp.flush()
            self.assertTrue(imp.store.path("find-a-tender", "quarantine").exists())
            self.assertEqual(imp.report["find-a-tender"]["quarantined"], 1)

    def test_pagination_loop_is_rejected(self):
        class Loop(FakeSession):
            def get(self, url, params=None, timeout=None):
                return FakeResponse({"releases": [release("o", "r", "2026-11-20T00:00:00Z")], "links": {"next": "https://www.find-tender.service.gov.uk/x"}})
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, Loop({}))
            self.assertFalse(imp.fetch_day("find-a-tender", dt.date(2026, 11, 20)))
            self.assertIn("loop", imp.report["find-a-tender"]["errors"][0].lower())

    def test_daily_window_overlaps_and_backfill_order(self):
        state = ip.empty_state()
        state["sources"]["find-a-tender"]["days"] = {"2026-11-22": {"status": "complete"}, "2026-11-10": {"status": "failed"}}
        with tempfile.TemporaryDirectory() as tmp:
            imp = make_importer(tmp, FakeSession({}), state=state)
            days = [str(d) for d in imp.daily_days("find-a-tender")]
            self.assertEqual(days, ["2026-11-10"] + [f"2026-11-{d}" for d in range(16, 26)])
            back = imp.backfill_days("find-a-tender")
            self.assertEqual([str(next(back)) for _ in range(3)], ["2026-11-24", "2026-11-23", "2026-11-21"])


def write_raw(tmp, source, releases):
    store = ps.LocalStore(Path(tmp) / "raw")
    by_month = {}
    for r in releases:
        by_month.setdefault(r["date"][:7], []).append({"source": source, "partition_day": r["date"][:10], "fetched_at": "x", "package": {}, "release": r})
    for m, rows in by_month.items():
        ps.write_partition(store.path(source, m), rows)
    return Path(tmp) / "raw"


SUPPLIER_PARTY = {"id": "GB-PPON-ABCD-1234-EFGH", "name": "Acme Ltd", "roles": ["supplier"],
                  "identifier": {"scheme": "GB-PPON", "id": "ABCD-1234-EFGH"}, "additionalIdentifiers": [{"scheme": "GB-COH", "id": "1234567"}]}


class BuilderTests(unittest.TestCase):
    def build(self, cf=(), fts=()):
        tmp = tempfile.mkdtemp()
        raw = write_raw(tmp, "contracts-finder", list(cf)) if cf else None
        raw = write_raw(tmp, "find-a-tender", list(fts)) if fts else raw
        out = Path(tmp) / "out"
        with patch.object(bp, "STATE_PATH", Path(tmp) / "none.json"), patch.object(bp, "LOG_PATH", Path(tmp) / "none2.json"):
            summary = bp.build(raw, out, generated_at="t")
        return summary, out

    def test_compiles_releases_and_keeps_value_types_separate(self):
        fts = [
            release("ocds-h6vhtk-1", "100-2026", "2026-01-05T00:00:00Z", tender={"title": "Ward refurbishment", "value": {"amount": 900000, "currency": "GBP"}},
                    buyer={"id": "B1", "name": "Example NHS Trust"}, parties=[{"id": "B1", "name": "Example NHS Trust", "roles": ["buyer"]}]),
            release("ocds-h6vhtk-1", "200-2026", "2026-03-01T00:00:00Z", tag=["award", "contract"], tender={"title": "Ward refurbishment"},
                    buyer={"id": "B1", "name": "Example NHS Trust"}, parties=[SUPPLIER_PARTY],
                    awards=[{"id": "1", "date": "2026-02-20", "value": {"amount": 850000, "currency": "GBP"}, "suppliers": [{"id": SUPPLIER_PARTY["id"], "name": "Acme Ltd"}]}],
                    contracts=[{"id": "1", "awardID": "1", "value": {"amount": 860000, "currency": "GBP"}, "period": {"startDate": "2026-04-01", "endDate": "2027-03-31"}}]),
        ]
        summary, out = self.build(fts=fts)
        rows = json.loads((out / "notices" / "2026-01.json").read_text())["rows"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["st"], r["n"], r["v"]), ("contract", 2, [900000, "GBP"]))
        self.assertEqual(r["aw"][0][1], [850000, "GBP"])  # award value
        self.assertEqual(r["aw"][0][2], [860000, "GBP"])  # contract value kept separately
        self.assertEqual(r["u"], "200-2026")  # stored relative to the Find a Tender notice base
        self.assertNotIn("id", r)
        self.assertEqual(summary["sources"]["find-a-tender"]["by_year"]["2026"]["award_value_gbp"], 850000)
        # Supplier is keyed by its Companies House number (zero-padded), linked through the PPON party.
        self.assertEqual(r["aw"][0][3], [["Acme Ltd", "GB-COH-01234567"]])
        sup = json.loads((out / "suppliers" / "index.json").read_text())["rows"]
        self.assertEqual(sup[0][:3], ["GB-COH-01234567", "Acme Ltd", 1])

    def test_framework_values_excluded_and_name_only_suppliers_not_merged(self):
        fts = [release("ocds-h6vhtk-2", "1", "2026-05-01T00:00:00Z", tag=["award"], tender={"title": "Framework", "techniques": {"hasFrameworkAgreement": True}},
                       awards=[{"id": "1", "value": {"amount": 5e9, "currency": "GBP"}, "suppliers": [{"name": "Nameonly Ltd"}]}])]
        cf = [release("ocds-b5fd17-x", "1", "2026-05-02T00:00:00Z", tag=["award"], tender={"title": "Other"},
                      awards=[{"id": "1", "value": {"amount": 100, "currency": "GBP"}, "suppliers": [{"name": "Nameonly Ltd"}]}])]
        summary, out = self.build(cf=cf, fts=fts)
        y = summary["sources"]["find-a-tender"]["by_year"]["2026"]
        self.assertEqual((y["award_value_gbp"], y["framework_awards"], y["framework_value_gbp"]), (0, 1, 5e9))
        self.assertEqual(summary["suppliers"]["identified"], 0)

    def test_two_companies_house_numbers_never_merge(self):
        p = {"id": "GB-PPON-SHARED-1", "name": "X", "identifier": {"scheme": "GB-PPON", "id": "SHARED-1"}, "additionalIdentifiers": [{"scheme": "GB-COH", "id": "11111111"}]}
        q = {"id": "GB-PPON-SHARED-1", "name": "Y", "identifier": {"scheme": "GB-PPON", "id": "SHARED-1"}, "additionalIdentifiers": [{"scheme": "GB-COH", "id": "22222222"}]}
        fts = [release("o1", "1", "2026-05-01T00:00:00Z", parties=[p]), release("o2", "1", "2026-05-01T00:00:00Z", parties=[q])]
        summary, _ = self.build(fts=fts)
        self.assertEqual(summary["quality"]["identifier_conflicts"], 1)

    def test_framework_and_call_off_classification(self):
        self.assertEqual(bp.framework_kind({"procurementMethodDetails": "Below threshold - award under framework"}), "call_off")
        self.assertEqual(bp.framework_kind({"procurementMethodDetails": "Call-off from a dynamic purchasing system"}), "call_off")
        self.assertEqual(bp.framework_kind({"lots": [{"techniques": {"hasFrameworkAgreement": True}}]}), "framework")
        self.assertIsNone(bp.framework_kind({"procurementMethodDetails": "Open procedure"}))

    def test_contract_value_used_when_award_has_none(self):
        fts = [release("o9", "1", "2026-07-01T00:00:00Z", tag=["award", "contract"], tender={"title": "T"},
                       awards=[{"id": "1", "suppliers": [{"name": "S"}]}],
                       contracts=[{"id": "1", "awardID": "1", "dateSigned": "2026-06-30", "value": {"amount": 500, "currency": "GBP"}}])]
        summary, out = self.build(fts=fts)
        row = json.loads((out / "notices" / "2026-07.json").read_text())["rows"][0]
        self.assertEqual(row["aw"][0][:2], ["2026-06-30", [500, "GBP"]])

    def test_identifier_cleaning(self):
        self.assertEqual(bp.clean_identifier("GB-COH", "2036219"), ("GB-COH", "02036219"))
        self.assertIsNone(bp.clean_identifier("GB-COH", "00000000"))
        self.assertIsNone(bp.clean_identifier("GB-PPON", "N/A"))
        self.assertEqual(bp.split_identifier("GB-PPON-PYNQ-4764-BRHM"), ("GB-PPON", "PYNQ-4764-BRHM"))

    def test_cross_source_duplicate_flagged_not_removed(self):
        award = {"id": "1", "value": {"amount": 1000, "currency": "GBP"}, "suppliers": [{"name": "Z"}]}
        cf = [release("ocds-b5fd17-d", "1", "2026-06-01T00:00:00Z", tag=["award"], tender={"title": "Road Works"}, buyer={"name": "Council A"}, awards=[award])]
        fts = [release("ocds-h6vhtk-d", "1", "2026-06-01T00:00:00Z", tag=["award"], tender={"title": "Road works"}, buyer={"name": "Council A"}, awards=[award])]
        summary, out = self.build(cf=cf, fts=fts)
        rows = json.loads((out / "notices" / "2026-06.json").read_text())["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(r for r in rows if r["src"] == "cf")["dup"], "fts:ocds-h6vhtk-d")

    def test_validate_refuses_shrinking_dataset(self):
        with self.assertRaises(SystemExit):
            bp.validate({"sources": {"a": {"processes": 10}}}, {"sources": {"a": {"processes": 100}}})


if __name__ == "__main__":
    unittest.main()
