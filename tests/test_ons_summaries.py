import unittest
from scripts.build_ons_summaries import summarize


class ONSSummaryTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "retrieved_at": "2026-11-23T00:00:00Z",
            "series": {
                "anbv": {
                    "label": "Receipts", "source": "https://example.org",
                    "observations": [
                        {"period": "2025 MAR", "value": 2},
                        {"period": "2025 APR", "value": 3},
                        {"period": "2025 MAY", "value": 4},
                    ],
                },
                "hf6x": {
                    "label": "Debt", "source": "https://example.org",
                    "observations": [
                        {"period": "2025 MAR", "value": 90},
                        {"period": "2025 APR", "value": 91},
                    ],
                },
            },
        }

    def test_fiscal_year_boundary_and_sum(self):
        years = summarize(self.payload, fiscal=True)["series"]["anbv"]["years"]
        self.assertEqual([p["financial_year"] for p in years], ["2024-25", "2025-26"])
        self.assertEqual([p["value"] for p in years], [2_000_000, 7_000_000])
        self.assertTrue(all(not p["complete"] for p in years))

    def test_debt_is_last_observation_not_sum(self):
        years = summarize(self.payload, fiscal=False)["series"]["hf6x"]["annual"]
        self.assertEqual(years[0]["value"], 91)

    def test_calendar_and_fiscal_differ(self):
        calendar = summarize(self.payload)["series"]["anbv"]["annual"]
        self.assertEqual(calendar[0]["value"], 9_000_000)

    def test_duplicate_month_is_rejected(self):
        self.payload["series"]["anbv"]["observations"].append({"period": "2025 APR", "value": 3})
        with self.assertRaises(ValueError):
            summarize(self.payload, fiscal=True)


if __name__ == "__main__":
    unittest.main()
