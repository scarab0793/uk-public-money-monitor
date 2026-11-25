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
        s = ot.parse_wide_table(df, ot.norm_month, "Table 1 HMRC")
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
            ["Total expenditure on services", 10, 20, 30, 40, 50, 60],
            ["(1) Footnote text", N, N, N, N, N, N],
        ])
        t = ot.parse_tes(df)
        self.assertEqual([r["level"] for r in t["rows"]], ["function", "component", "total"])
        self.assertEqual(t["rows"][0]["values"][-1], ["2025-26", "plans", 6.0])
        self.assertEqual(t["rows"][0]["values"][0], ["2020-21", "outturn", 1.0])


if __name__ == "__main__":
    unittest.main()
