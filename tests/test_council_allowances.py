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

    def test_pdf_columns_across_pages(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab not installed")
        import io as _io
        buf = _io.BytesIO()
        c = canvas.Canvas(buf)
        xs = [200, 290, 380, 470]
        def row(y, name, vals):
            c.drawString(40, y, name)
            for v, x in zip(vals, xs):
                if v:
                    c.drawRightString(x, y, v)
        c.drawString(40, 800, "Notice is given that in 2025/2026 the following sums were paid under the scheme of allowances")
        for x, t in [(40, "COUNCILLOR"), (160, "Basic"), (250, "Special"), (340, "Dependents'"), (440, "TOTAL")]:
            c.drawString(x, 740, t)
        for x, t in [(160, "Allowance"), (250, "Responsibility"), (340, "Carers'")]:
            c.drawString(x, 728, t)
        for x, t in [(250, "Allowance"), (340, "Allowance")]:
            c.drawString(x, 716, t)
        row(690, "ADAIR R*", ["£1,683.40", "£1,302.66", "", "£2,986.06"])
        row(676, "ADEGOKE C", ["£15,776.61", "£8,455.95", "£60.00", "£24,292.56"])
        row(662, "ALLAN P*", ["£1,683.40", "", "", "£1,683.40"])
        c.showPage()
        row(800, "CARLTON S*", ["£1,683.40", "£2,605.42", "", "£4,288.82"])
        row(786, "TOTAL", ["£20,826.81", "£12,364.03", "£60.00", "£33,250.84"])
        c.save()
        g = ca.grid_from_pdf(buf.getvalue())[0]
        self.assertEqual(g[0], ["COUNCILLOR", "Basic Allowance", "Special Responsibility Allowance", "Dependents' Carers' Allowance", "TOTAL"])
        s = ca.summarise(ca.read_grid(g))
        self.assertEqual([x["name"] for x in s["councillors"]], ["ADAIR R*", "ADEGOKE C", "ALLAN P*", "CARLTON S*"])
        self.assertEqual(s["total_check"]["mismatches"], [])
        self.assertEqual(s["totals_by_category"]["carers"], 60.0)

    def test_long_format(self):
        g = [["COUNCILLOR", "TYPE OF PAYMENT", "AMOUNT"]] + [[n, "Members' Basic Allowance", "100"] for n in "ABCDE"] + [["", "Special Responsibility Allowance", "50"]]
        s = ca.summarise(ca.read_grid(g))
        self.assertEqual(s["councillors"][-1]["amounts"], {"Members' Basic Allowance": 100.0, "Special Responsibility Allowance": 50.0})
        self.assertEqual(s["total"], 550.0)


if __name__ == "__main__":
    unittest.main()
