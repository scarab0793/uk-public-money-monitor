"""Offline tests for ONS ingestion; no external service required."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "fetch_ons.py"
spec = importlib.util.spec_from_file_location("fetch_ons", MODULE)
ons = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ons)

class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): pass

class IngestionTests(unittest.TestCase):
    def test_valid_months(self):
        months = [{"date": f"2025 {m}", "value": str(90+i/10)} for i,m in enumerate(("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"))]
        class Response(FakeResponse):
            def read(self): return json.dumps({"months": months}).encode()
        with patch.object(ons.urllib.request, "urlopen", return_value=Response()):
            result = ons.get_series("hf6x")
        self.assertEqual(len(result["observations"]), 12)
        self.assertEqual(result["observations"][-1]["period"], "2025 DEC")
    def test_reverse_chronological_feed_is_sorted(self):
        months = [{"date": f"2025 {m}", "value": "90"} for m in
                  ("DEC","NOV","OCT","SEP","AUG","JUL","JUN","MAY","APR","MAR","FEB","JAN")]
        class Response(FakeResponse):
            def read(self): return json.dumps({"months": months}).encode()
        with patch.object(ons.urllib.request, "urlopen", return_value=Response()):
            result = ons.get_series("hf6x")
        self.assertEqual(result["observations"][0]["period"], "2025 JAN")
        self.assertEqual(result["observations"][-1]["period"], "2025 DEC")

    def test_failure_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            old = Path(folder) / "ons-public-finances.json"
            old.write_text('{"previous":"valid"}')
            with patch.object(ons, "OUT", old), patch.object(ons, "get_series", side_effect=ValueError("bad feed")):
                with self.assertRaises(ValueError): ons.main()
            self.assertEqual(json.loads(old.read_text()), {"previous":"valid"})

if __name__ == "__main__":
    unittest.main()
