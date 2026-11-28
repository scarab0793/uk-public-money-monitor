import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import import_representatives_pay as rp  # noqa: E402

SPEND_2122 = ("﻿MP's name,Constituency,Office maximum budget available,Reason for budget set,Office spend,Remaining office budget,"
              "Staffing maximum budget available,Reason for budget set,Staffing spend,Remaining staffing budget,Wind-up maximum budget available,"
              "Reason for budget set,Wind-up spend,Remaining wind-up budget,Subtotal of office running costs,Accommodation maximum budget available,"
              "Reason for budget set,Accommodation spend,Remaining accommodation budget,Travel and subsistence maximum budget available,"
              "Travel and subsistence spend,Other costs maximum budget available,Other costs spend,Subtotal of other parliamentary costs,"
              "Overall total spend for this financial year,pID\r\n"
              "A Member,Somewhere,\"£28,800.00\",Standard,\"£20,000.00\",\"£8,800.00\",\"£200,000.00\",Standard,\"£190,000.50\",\"£9,999.50\","
              "N/A,N/A,N/A,N/A,\"£210,000.50\",\"£23,000.00\",London,\"£22,000.00\",\"£1,000.00\",N/A,\"£4,000.00\",N/A,£12.34,\"£26,012.34\",\"£236,012.84\",42\r\n")
SPEND_2526 = ("﻿﻿MP's name,Constituency,Office budget,Reason for budget set,Office spend,Remaining office budget,Staffing budget,Reason for budget set,"
              "Staffing spend,Remaining staffing budget,Winding-up budget,Reason for budget set,Winding-up spend,Remaining winding-up budget,"
              "Accommodation budget,Reason for budget set,Accommodation spend,Remaining accommodation budget,Travel and subsistence (uncapped),"
              "Other costs (uncapped),pID\r\n"
              "A Member,Somewhere,\"£30,000.00\",Standard,\"£25,000.00\",\"£5,000.00\",\"£220,000.00\",Standard,\"£210,000.00\",\"£10,000.00\","
              "N/A,N/A,N/A,N/A,£0.00,N/A,£0.00,£0.00,\"£3,500.00\",£10.00,42\r\n")
INFO = ("﻿MP's Name,Constituency,Basic salary,Additional salary,Reason for additional salary,Resettlement/Loss-of-office Payment,LALP amount,"
        "LALP period,Connected party name,Connected party job title,Connected party full/part time,Connected Party Employed for Whole Year,"
        "Connected party salary,Other staff job title,Other staff full/part time,Other staff employed for the whole year,Advance loan outstanding,"
        "Repayment of advance loan,Office deposit loan outstanding,Repayment of office deposit loan,Accommodation loan outstanding,"
        "Repayment of accommodation loan,Contingency amount applied for,Type of request,Contingency amount granted,Reward and recognition payments,"
        "Debts incurred by the MP which IPSA has written off,pID\r\n"
        "A Member,Somewhere,\"£91,346.04\",\"£7,894.10\",Committee Chair,£0.00,\"£4,680.00\",April 24 - March 25,Pat Member,Office Manager,Full Time,Yes,"
        "\"£50,000.00 to £54,999.99\",Caseworker,Permanent Full Time,Yes,£0.00,£0.00,£0.00,£0.00,£0.00,\"-£3,865.38\",,,,£0.00,£0.00,42\r\n")
CLAIMS = ('"Parliamentary ID","Year","Date","Claim Number","Name","Constituency","Category","Cost Type","Short Description","Details","Journey Type",'
          '"From","To","Travel","Nights","Mileage","Amount Claimed","Amount Paid","Amount Not Paid","Amount Repaid","Status","Reason If Not Paid",'
          '"Supply Month","Supply Period"\n'
          '42,"24_25","08/10/2024","1-1","A Member","Somewhere","Accommodation","Rent","","Rent, monthly","","","","",0,0,1000,1000,0,0,"Paid","","",0\n'
          '42,"24_25","09/10/2024","1-2","A Member","Somewhere","Accommodation","Rent","","","","","","",0,0,500,500,0,100,"Repaid","","",0\n'
          '42,"24_25","10/10/2024","1-3","A Member","Somewhere","MP Travel","Rail","","","","London","Leeds","",0,0,80,0,80,0,"Not Paid","Late","",0\n')


class RepresentativesPayTests(unittest.TestCase):
    def test_money(self):
        self.assertEqual(rp.money("£1,234.56"), 1234.56)
        self.assertEqual(rp.money("-£3,865.38"), -3865.38)
        self.assertIsNone(rp.money("N/A"))
        self.assertIsNone(rp.money(""))

    def test_total_spend_old_layout(self):
        s = rp.parse_total_spend(rp.read_csv(SPEND_2122))["42"]["budgets"]
        self.assertEqual(s["office"], dict(budget=28800.0, reason="Standard", spend=20000.0, remaining=8800.0))
        self.assertEqual(s["staffing"]["spend"], 190000.5)
        self.assertEqual(s["accommodation"]["reason"], "London")
        self.assertEqual(s["travel"]["spend"], 4000.0)
        self.assertEqual(s["other"]["spend"], 12.34)
        self.assertIsNone(s["winding_up"]["budget"])

    def test_total_spend_new_layout(self):
        s = rp.parse_total_spend(rp.read_csv(SPEND_2526))["42"]["budgets"]
        self.assertEqual(s["staffing"], dict(budget=220000.0, reason="Standard", spend=210000.0, remaining=10000.0))
        self.assertEqual(s["travel"]["spend"], 3500.0)
        self.assertEqual(s["other"]["spend"], 10.0)

    def test_other_info(self):
        o = rp.parse_other_info(rp.read_csv(INFO))["42"]
        self.assertEqual(o["basic_salary"], 91346.04)
        self.assertEqual(o["additional_salary"], 7894.10)
        self.assertEqual(o["additional_salary_reason"], "Committee Chair")
        self.assertEqual(o["lalp"], 4680.0)
        self.assertEqual(o["connected_party"], ["Pat Member", "Office Manager", "£50,000.00 to £54,999.99"])

    def test_claims_net_of_repayments(self):
        c, n = rp.aggregate_claims(CLAIMS)
        self.assertEqual(n, 3)
        self.assertEqual(c["42"]["by_category"]["Accommodation"]["Rent"], 1400.0)
        self.assertEqual(c["42"]["by_category"]["MP Travel"]["Rail"], 0.0)
        self.assertEqual(c["42"]["not_paid"], 80.0)
        self.assertEqual(c["42"]["claims"], 3)

    def test_tables_and_years(self):
        page = ('<table><thead><tr><td>​Date</td><td>​Annual salary</td></tr></thead><tbody><tr><td>April 2026</td><td>£98,599</td></tr></tbody></table>'
                '<a href="/api/download?type=totalSpend&amp;year=25_26">x</a><a href="/api/download?type=otherInfo&amp;year=25_26">y</a>')
        self.assertEqual(rp.tables(page)[0], [["Date", "Annual salary"], ["April 2026", "£98,599"]])
        self.assertEqual(rp.discover_years(page), {"25_26": {"totalSpend", "otherInfo"}})
        self.assertEqual(rp.fy_label("25_26"), "2025-26")


if __name__ == "__main__":
    unittest.main()
