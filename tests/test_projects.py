"""Offline tests for the source-attributed public project importer."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_projects", ROOT / "scripts" / "build_projects.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ProjectImporterTests(unittest.TestCase):
    def sample(self):
        return {"id":"project-1","name":"Test public project","department":"Test department",
                "sector":"Transport","status":"delivery","source_url":"https://example.gov.uk/report",
                "source_title":"Official test document","source_as_of":"2025-06-30",
                "original_budget_gbp":"1000000","current_forecast_gbp":"1250000",
                "original_completion":"2025-01-01","forecast_completion":"2025-07-01"}

    def test_valid_project(self):
        row = mod.validate(self.sample(),2)
        self.assertEqual(row["original_budget_gbp"],1000000)
        self.assertEqual(row["forecast_completion"],"2025-07-01")
        self.assertIsNone(row["actual_spend_gbp"])

    def test_reject_missing_source(self):
        row=self.sample();row["source_url"]=""
        with self.assertRaises(ValueError): mod.validate(row,2)

    def test_reject_negative_amount(self):
        row=self.sample();row["original_budget_gbp"]="-1"
        with self.assertRaises(ValueError): mod.validate(row,2)

    def test_publish_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            csvfile=Path(tmp)/"projects.csv"
            row=self.sample()
            with csvfile.open("w",newline="",encoding="utf-8") as file:
                writer=csv.DictWriter(file,fieldnames=list(row))
                writer.writeheader();writer.writerow(row)
            output=Path(tmp)/"projects.json"
            with patch.object(mod,"OUT",output):mod.build(csvfile)
            data=json.loads(output.read_text())
            self.assertEqual(data["project_count"],1)
            with csvfile.open("a",newline="",encoding="utf-8") as file:
                writer=csv.DictWriter(file,fieldnames=list(row));writer.writerow(row)
            with patch.object(mod,"OUT",output):
                with self.assertRaises(ValueError):mod.build(csvfile)
            self.assertEqual(json.loads(output.read_text())["project_count"],1)

if __name__ == "__main__":
    unittest.main()
