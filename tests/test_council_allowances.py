import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import import_council_allowances as ca  # noqa: E402

LAYOUT = """                      Councillors Allowances and Expenses Payments 2024-25.xlsx



                                                    Special                Mileage, Travel,
                                              Responsibility                   Expenses &
Last Name, First Name        Basic Pay Only      Allowance           Total    Subsistence           Total
ALLAWAY MARTIN CAROLE          £12,075.00       £20,958.96     £33,033.96            £0.00    £33,033.96
BABBAGE MATT                   £12,075.00        £7,140.00     £19,215.00            £0.00    £19,215.00
BAKER PAUL                     £12,075.00            £0.00     £12,075.00            £0.00    £12,075.00
FIFIELD STEPHAN                £12,075.00       £20,958.96     £33,033.96         £407.25     £33,441.21
"""


class CouncilAllowanceTests(unittest.TestCase):
    def test_years(self):
        for t in ["2025-26", "2025/2026", "Expenses and allowances 2025 to 2026", "membersallowances202526.pdf",
                  "1 April 2025 to 31 March 2026", "council-members-allowances-2025-2026.xlsx"]:
            self.assertEqual(ca.year_of(t), "2025-26", t)
        self.assertIsNone(ca.year_of("October 2026"))

    def test_amounts(self):
        self.assertEqual(ca.amount("£1,234.50"), 1234.5)
        self.assertEqual(ca.amount("-"), 0.0)
        self.assertEqual(ca.amount("(12.00)"), -12.0)
        self.assertTrue(ca.is_amount("£0.00"))
        self.assertFalse(ca.is_amount("Cllr Smith"))

    def test_categories(self):
        self.assertEqual(ca.category("Basic Allowance"), "basic")
        self.assertEqual(ca.category("Special Responsibility Allowance"), "special_responsibility")
        self.assertEqual(ca.category("Mileage, Travel, Expenses & Subsistence"), "travel")
        self.assertEqual(ca.category("Total"), "total")
        self.assertEqual(ca.category("Total (2)"), "total")
        self.assertEqual(ca.category("Carers allowance"), "carers")

    def test_pdf_layout_and_totals(self):
        g = ca.grid_from_layout_text(LAYOUT)[0]
        self.assertEqual(g[0], ["Last Name, First Name", "Basic Pay Only", "Special Responsibility Allowance", "Total",
                                "Mileage, Travel, Expenses & Subsistence", "Total"])
        s = ca.summarise(ca.read_grid(g))
        self.assertEqual(len(s["councillors"]), 4)
        self.assertEqual(s["total_check"]["mismatches"], [])
        self.assertEqual(s["councillors"][3]["total"], 33441.21)
        self.assertEqual(s["totals_by_category"], {"basic": 48300.0, "special_responsibility": 49057.92, "travel": 407.25})

    def test_html_table(self):
        page = ("<table><tr><th>Member</th><th>Basic allowance £</th><th>Special Responsibility Allowance £</th></tr>"
                + "".join(f"<tr><td>Cllr {n}</td><td>15,141.96</td><td>{v}</td></tr>" for n, v in [("A", "-"), ("B", "6,188.04"), ("C", "7,727.04"), ("D", "-")])
                + "<tr><td>Total</td><td>60,567.84</td><td>13,915.08</td></tr></table>")
        s = ca.summarise(ca.read_grid(ca.grids_from_html(page)[0]))
        self.assertEqual([c["name"] for c in s["councillors"]], ["Cllr A", "Cllr B", "Cllr C", "Cllr D"])
        self.assertEqual(s["councillors"][1]["total"], 21330.0)
        self.assertEqual(s["total"], 74482.92)


if __name__ == "__main__":
    unittest.main()
