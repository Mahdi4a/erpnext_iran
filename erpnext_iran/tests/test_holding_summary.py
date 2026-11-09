import unittest
from unittest.mock import patch

import frappe

from erpnext_iran.erpnext_iran.report.holding_summary import holding_summary as report


def row(company, currency="IRR", **values):
	base = {"company": company, "currency": currency, "branches": 1, "income": 0, "gross": 0, "net": 0, "margin": 0, "cash": 0, "receivable": 0, "payable": 0, "stock": 0}
	return {**base, **values}


class TestScope(unittest.TestCase):
	def test_no_company_means_every_company(self):
		with patch.object(report.frappe, "get_all", return_value=["A", "B"]) as get_all:
			self.assertEqual(report.companies_in_scope(None), ["A", "B"])
		self.assertEqual(get_all.call_args.kwargs["order_by"], "lft")

	def test_a_group_brings_in_the_companies_below_it(self):
		with patch.object(report.frappe.db, "get_value", return_value=(1, 8)), patch.object(report.frappe, "get_all", return_value=["Holding", "Sub 1", "Sub 2"]) as get_all:
			self.assertEqual(report.companies_in_scope("Holding"), ["Holding", "Sub 1", "Sub 2"])
		self.assertEqual(get_all.call_args.kwargs["filters"], {"lft": [">=", 1], "rgt": ["<=", 8]})

	def test_an_unknown_company_is_just_itself(self):
		with patch.object(report.frappe.db, "get_value", return_value=None):
			self.assertEqual(report.companies_in_scope("X"), ["X"])


class TestTotals(unittest.TestCase):
	def test_total_row_works_out_the_margin_from_the_totals(self):
		total = report.total_row([row("A", income=100, net=10), row("B", income=300, net=90)])
		self.assertEqual((total["income"], total["net"]), (400, 100))
		self.assertAlmostEqual(total["margin"], 25)

	def run_with(self, currencies):
		companies = [f"C{i}" for i in range(len(currencies))]
		with patch.object(report, "companies_in_scope", return_value=companies), patch.object(report.frappe.db, "sql", side_effect=[[], [], []]), patch.object(
			report.frappe, "get_cached_value", side_effect=lambda dt, name, field: currencies[companies.index(name)]
		):
			return report.get_data(frappe._dict(from_date="2026-01-01", to_date="2026-12-31"))

	def test_no_total_for_companies_in_different_currencies(self):
		rows = self.run_with(["IRR", "USD"])
		self.assertEqual(len(rows), 2)
		self.assertNotIn("Total", [r["company"] for r in rows])

	def test_a_total_for_companies_in_one_currency(self):
		rows = self.run_with(["IRR", "IRR"])
		self.assertEqual(len(rows), 3)


class TestAgainstTheLedger(unittest.TestCase):
	def test_every_company_matches_the_net_profit_report(self):
		from erpnext_iran.erpnext_iran.report.branch_net_profit.branch_net_profit import execute as branch_net

		rows = report.get_data(frappe._dict(from_date="2000-01-01", to_date="2100-01-01"))
		for r in rows:
			if r["company"] == "Total":
				continue
			branches = branch_net({"company": r["company"], "from_date": "2000-01-01", "to_date": "2100-01-01"})[1]
			total = [b for b in branches if b["branch"] == "Total"]
			expected = total[0] if total else (branches[0] if branches else {"income": 0, "net": 0})
			self.assertAlmostEqual(r["income"], expected["income"], places=2)
			self.assertAlmostEqual(r["net"], expected["net"], places=2)
