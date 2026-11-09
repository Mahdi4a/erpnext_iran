import unittest

import frappe

from erpnext_iran.erpnext_iran.report.branch_profit.branch_profit import execute


def filters(**extra):
	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
	return {"company": company, "from_date": "2000-01-01", "to_date": "2100-01-01", **extra}


class TestBranchProfit(unittest.TestCase):
	def test_every_grouping_adds_up_to_the_same_total(self):
		totals = []
		for group in ("Branch", "Branch and Day", "Branch and Item Group"):
			_columns, data = execute(filters(group_by=group))
			totals.append(round(sum(row["net_sales"] for row in data if row["branch"] != "Total"), 2))
		self.assertEqual(len(set(totals)), 1, totals)

	def test_net_sales_match_the_invoice_lines(self):
		_columns, data = execute(filters())
		expected = frappe.db.sql(
			"""select ifnull(sum(item.base_net_amount), 0) from `tabSales Invoice Item` item
			join `tabSales Invoice` si on si.name = item.parent where si.docstatus = 1 and si.company = %s""",
			filters()["company"],
		)[0][0]
		self.assertAlmostEqual(sum(row["net_sales"] for row in data if row["branch"] != "Total"), float(expected), places=2)

	def test_profit_is_sales_minus_cost(self):
		_columns, data = execute(filters())
		for row in data:
			self.assertAlmostEqual(row["profit"], row["net_sales"] - row["cost"], places=2)

	def test_the_total_row_is_not_a_sum_of_percentages(self):
		_columns, data = execute(filters())
		*branches, total = data
		self.assertEqual(total["branch"], "Total")
		self.assertAlmostEqual(total["net_sales"], sum(row["net_sales"] for row in branches), places=2)
		if total["net_sales"]:
			self.assertAlmostEqual(total["margin"], total["profit"] / total["net_sales"] * 100, places=6)

	def test_an_unknown_grouping_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			execute(filters(group_by="Customer"))
