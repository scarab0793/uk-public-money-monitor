"""Offline tests for HMRC receipts and Treasury TES table parsing."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import import_official_tables as ot  # noqa: E402

N = float("nan")


class ParserTests(unittest.TestCase):
    def test_hmrc_wide_table_keeps_missing_as_null_and_negatives(self):
        df = pd.DataFrame([
            ["Table 1. HM Revenue and Customs receipts", N, N, N],
            ["Table 1 HMRC Receipts by month", "Total HMRC Receipts", "Income Tax", "Vaping Products Duty"],
            ["April 2017", 56228, 16222, "[X]"],
            ["May 2017", 42703, -106, "[x]"],
            ["Notes", N, N, N],
        ])
        s = ot.parse_wide_table(df, ot.norm_month, "Table 1")
        self.assertEqual(s["Total HMRC Receipts"], [["2017-04", 56228.0], ["2017-05", 42703.0]])
        self.assertEqual(s["Income Tax"][1], ["2017-05", -106.0])
        self.assertEqual(s["Vaping Products Duty"], [["2017-04", None], ["2017-05", None]])

    def test_financial_year_labels(self):
        self.assertEqual(ot.norm_fy("2006 to 2007"), "2006-07")
        self.assertEqual(ot.norm_fy("2024-25"), "2024-25")
        self.assertIsNone(ot.norm_fy("Notes"))

    def test_tes_table_separates_outturn_plans_and_components(self):
        df = pd.DataFrame([
            ["Table 9 Public sector expenditure on services by function, £ billion", N, N, N, N, N, N],
            [N, "Accredited Official Statistics", N, N, N, N, N],
            [N, "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"],
            [N, "outturn", "outturn", "outturn", "outturn", "outturn", "plans"],
            ["1. General public services", 1, 2, 3, 4, 5, 6],
            ["of which: debt interest", 0.5, 1, 1, 1, 1, 1],
            ["Public sector expenditure on services", 10, 20, 30, 40, 50, 60],
            ["Accounting adjustments", 1, 1, 1, 1, 1, 1],
            ["Total Managed Expenditure(7)", 11, 21, 31, 41, 51, 61],
            ["(1) Footnote text", N, N, N, N, N, N],
        ])
        t = ot.parse_tes(df)
        self.assertEqual([r["level"] for r in t["rows"]], ["function", "component", "total", "adjustment", "total"])
        self.assertEqual(t["rows"][0]["values"][-1], ["2025-26", "plans", 6.0])
        self.assertEqual(t["rows"][0]["values"][0], ["2020-21", "outturn", 1.0])
        self.assertEqual([r["name"] for r in t["rows"]][::4], ["General public services", "Total Managed Expenditure"])

    def test_cra_two_unit_blocks(self):
        df = pd.DataFrame([
            ["Table A.1b Total UK identifiable expenditure on services by country and region", N, N, N, N, N, N],
            [N, N, N, "£ per head", N, N, "Index (UK identifiable expenditure = 100)"],
            [N, "Accredited Official Statistics", N, N, "Accredited Official Statistics", N, N],
            [N, "2023-24\noutturn", "2024-25\noutturn", "2025-26\noutturn", "2023-24\noutturn", "2024-25\noutturn", "2025-26\noutturn"],
            ["North East", 13605, 14241, 14908, 105, 105, 104],
            ["England", 12598, 13133, 13902, 97, 97, 97],
            ["UK identifiable expenditure", 13000, 13600, 14284, 100, 100, 100],
            ["(1) note", N, N, N, N, N, N],
        ])
        t = ot.parse_cra_table(df)
        self.assertEqual(t["units"], ["£ per head", "Index (UK identifiable expenditure = 100)"])
        self.assertEqual([r["level"] for r in t["rows"]], ["english_region", "nation", "total_or_other"])
        self.assertEqual(t["rows"][0]["blocks"][0][-1], ["2025-26", "outturn", 14908.0])
        self.assertEqual(t["rows"][0]["blocks"][1][0], ["2023-24", "outturn", 105.0])

    def test_header_table(self):
        df = pd.DataFrame([["Table 9: Area council tax", N, N, N], ["note", N, N, N],
                           ["E Code", "Authority", "Band A", "Band D"], ["E5011", "Camden", 1471.7, 2207.55], ["E5010", "City of London", "[x]", 1329.56], [N, N, N, N]])
        t = ot.parse_header_table(df)
        self.assertEqual(t["columns"], ["E Code", "Authority", "Band A", "Band D"])
        self.assertEqual(t["rows"][1], {"E Code": "E5010", "Authority": "City of London", "Band A": None, "Band D": 1329.56})

    def test_cra_by_function(self):
        df = pd.DataFrame([["Table A.15 UK identifiable expenditure on services by function per head", N, N, N, N, N, N],
                           ["note", N, N, N, N, N, "£ per head"],
                           [N, "1. General public services", " of which: public and common services", "2. Defence", "7. Health", "9. Education", "Total Expenditure on Services"],
                           [N, N, N, N, N, N, N],
                           ["2025-26", N, N, N, N, N, N],
                           ["North East", 161, 160, 8, 3382, 1476, N],
                           ["Scotland", 200, 150, 9, 3900, 1500, N]])
        t = ot.parse_cra_by_function(df)
        self.assertEqual([f["name"] for f in t["functions"]], ["General public services", "public and common services", "Defence", "Health", "Education"])
        self.assertEqual(t["years"]["2025-26"][0]["values"]["Health"], 3382.0)
        self.assertEqual(t["years"]["2025-26"][1]["level"], "nation")

    def test_dwp_table_years_flags_sections_and_zero_kept(self):
        df = pd.DataFrame([
            ["Contents page", "Information", N, N, N, N],
            ["Autumn Forecast", "Table 1a: Expenditure by benefit,", N, "2024/25", "2025/26", "2026/27"],
            ["2026", "£ million, nominal terms", "Benefit type", "Outturn", "Outturn", "Forecast"],
            [N, N, N, N, N, N],
            [N, "Attendance Allowance", "(NC / NIR)", 7000.5, 7400, 7900],
            [N, "Working age", N, N, N, N],
            [N, "Universal Credit", "(IR)", 0, "..", 90000],
            [N, "Notes", N, N, N, N],
            [N, "Should not appear", N, 1, 2, 3],
        ])
        t = ot.parse_dwp_table(df)
        self.assertEqual(t["years"], ["2024-25", "2025-26", "2026-27"])
        self.assertEqual(t["forecast"], [False, False, True])
        self.assertEqual(t["unit"], "£ million, nominal terms")
        self.assertEqual(t["title"], "Table 1a: Expenditure by benefit")
        self.assertEqual([r["name"] for r in t["rows"]], ["Attendance Allowance", "Universal Credit"])
        self.assertEqual(t["rows"][1]["section"], "Working age")
        self.assertEqual(t["rows"][1]["values"], [0.0, None, 90000.0])
        self.assertEqual(t["rows"][0]["marker"], "(NC / NIR)")

    def test_rsx_services_measures_and_missing(self):
        df = pd.DataFrame([
            ["Worksheet 2", N, N, N, N, N, N, N, N, N],
            ["E-code", "ONS Code", "Local authority", "Notes", "Class", "Education services - Employees (C1)",
             "Education services - Total Expenditure (C3 = C1 + C2)", "Education services - Total Income (C6 = C4 + C5)",
             "Education services - Net Current Expenditure (C7 = C3 - C6)", "Public Health - Net Current Expenditure (C7 = C3 - C6)"],
            ["E3831", "E07000223", "Adur", N, "SD", 5, 345, 657, -312, 0],
            ["E9999", "E0", "Late Council", "M", "UA", N, N, N, N, "[x]"],
            ["England", N, N, N, N, 1, 2, 3, 4, 5],
        ])
        t = ot.parse_rsx(df)
        self.assertEqual(t["services"], ["Education services", "Public Health"])
        self.assertEqual(t["authorities"][0]["values"]["Education services"], [345.0, 657.0, -312.0])
        self.assertEqual(t["authorities"][0]["values"]["Public Health"], [None, None, 0.0])
        self.assertEqual(t["authorities"][1]["values"]["Education services"], [None, None, None])
        self.assertEqual(t["authorities"][1]["notes"], "M")
        self.assertEqual(len(t["authorities"]), 2)
        self.assertEqual(t["identity_failures"], 0)


if __name__ == "__main__":
    unittest.main()
