import unittest

import frappe

from erpnext_iran.erpnext_iran.report.branch_net_profit.branch_net_profit import execute


def filters(**extra):
	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
	return {"company": company, "from_date": "2000-01-01", "to_date": "2100-01-01", **extra}


def ledger(root_type, company):
	return float(
		frappe.db.sql(
			"""select ifnull(sum(case when a.root_type = 'Income' then gl.credit - gl.debit else gl.debit - gl.credit end), 0)
			from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
			where gl.is_cancelled = 0 and gl.company = %s and a.root_type = %s and ifnull(gl.voucher_type, '') != 'Period Closing Voucher'""",
			(company, root_type),
		)[0][0]
	)


class TestBranchNetProfit(unittest.TestCase):
	def test_income_and_expenses_equal_the_ledger(self):
		_columns, data = execute(filters())
		*rows, total = data
		self.assertEqual(total["branch"], "Total")
		self.assertAlmostEqual(total["income"], ledger("Income", filters()["company"]), places=2)
		self.assertAlmostEqual(total["cogs"] + total["expenses"], ledger("Expense", filters()["company"]), places=2)

	def test_net_is_income_less_cost_less_expenses(self):
		for row in execute(filters())[1]:
			self.assertAlmostEqual(row["net"], row["income"] - row["cogs"] - row["expenses"], places=2)
			self.assertAlmostEqual(row["gross"], row["income"] - row["cogs"], places=2)

	def test_the_months_add_up_to_the_branches(self):
		by_branch = execute(filters())[1]
		by_month = execute(filters(group_by="Branch and Month"))[1]
		self.assertAlmostEqual(by_branch[-1]["net"], by_month[-1]["net"], places=2)
		self.assertTrue(all("month" in row for row in by_month))

	def test_an_unknown_grouping_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			execute(filters(group_by="Item"))

	def test_what_no_branch_carries_is_shown_not_dropped(self):
		names = [row["branch"] for row in execute(filters())[1]]
		unallocated = frappe.db.sql(
			"""select count(*) from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
			where gl.is_cancelled = 0 and ifnull(gl.cost_center, '') = '' and gl.company = %s and a.root_type in ('Income', 'Expense')""",
			filters()["company"],
		)[0][0]
		if unallocated:
			self.assertIn("Not charged to a branch", names)
