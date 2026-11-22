"""Tests for official NISTA project mapping; no network calls."""
import importlib.util
import io
import csv
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("fetch_nista",Path(__file__).resolve().parents[1]/"scripts"/"fetch_nista.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NistaTests(unittest.TestCase):
    def test_catalogue_extracts_realistic_headers(self):
        records=[]
        for n in range(25):
            records.append({"Project Name":f"Project {n}","Department":"Transport",
                            "Project Description":"Upgrade railway signalling","Annual Report Category":"Infrastructure"})
        data={"records":records,"retrieved_at":"2026-11-22T00:00:00+00:00"}
        result=module.make_catalogue(data)
        self.assertEqual(result["project_count"],25)
        self.assertEqual(result["projects"][0]["description"],"Upgrade railway signalling")
        self.assertIsNone(result["projects"][0]["original_budget_gbp"])

    def test_explicit_millions_conversion(self):
        self.assertEqual(module.millions_to_gbp("1,234.5"),1234500000)
        self.assertIsNone(module.millions_to_gbp("Not Set"))
        self.assertIsNone(module.millions_to_gbp("Redacted"))

    def test_financial_year_not_mislabelled_as_total_budget(self):
        records=[{"Project Name":f"Project {n}","Department":"Transport",
                  "Financial Year Baseline (£m)":"10","Financial Year Forecast (£m)":"12",
                  "Whole Life Cost (£m)":"250"} for n in range(25)]
        result=module.make_catalogue({"records":records,"retrieved_at":"2026-11-22T00:00:00+00:00"})
        project=result["projects"][0]
        self.assertEqual(project["financial_year_baseline_gbp"],10000000)
        self.assertEqual(project["financial_year_forecast_gbp"],12000000)
        self.assertEqual(project["whole_life_cost_gbp"],250000000)
        self.assertIsNone(project["original_budget_gbp"])

    def test_missing_names_cannot_be_published(self):
        data={"records":[{"Unnamed column":"Something"} for _ in range(25)],
              "retrieved_at":"2026-11-22T00:00:00+00:00"}
        with self.assertRaises(ValueError):
            module.make_catalogue(data)

    def test_reject_html_or_short_payload(self):
        with self.assertRaises(ValueError):
            module.build(b"<html>Not found</html>")

if __name__=="__main__":
    unittest.main()
