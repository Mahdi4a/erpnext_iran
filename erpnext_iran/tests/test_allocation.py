import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import allocation


class TestDistribute(unittest.TestCase):
	def test_always_exactly_one_hundred(self):
		for amounts in ({"a": 1, "b": 1, "c": 1}, {"a": 1, "b": 2, "c": 3, "d": 7}, {"a": 33.3333, "b": 66.6667}, {"a": 1, "b": 0, "c": 0}, {"a": 1e9, "b": 1}):
			with self.subTest(amounts):
				share = allocation.distribute(amounts)
				self.assertAlmostEqual(sum(share.values()), 100, places=6)
				self.assertTrue(all(v >= 0 for v in share.values()))

	def test_shares_follow_the_sales(self):
		self.assertEqual(allocation.distribute({"a": 750, "b": 250}), {"a": 75.0, "b": 25.0})

	def test_three_equal_branches_get_33_33_33_34_not_more_than_100(self):
		share = allocation.distribute({"a": 1, "b": 1, "c": 1})
		self.assertEqual(sorted(share.values()), [33.33, 33.33, 33.34])

	def test_nobody_sold_anything_splits_equally(self):
		self.assertEqual(allocation.distribute({"a": 0, "b": 0}), {"a": 50.0, "b": 50.0})

	def test_negative_sales_count_as_nothing_and_empty_is_empty(self):
		self.assertEqual(allocation.distribute({"a": -50, "b": 100}), {"a": 0.0, "b": 100.0})
		self.assertEqual(allocation.distribute({}), {})


class TestSuggest(unittest.TestCase):
	def run_suggest(self, sales):
		with patch.object(allocation.frappe, "has_permission"), patch.object(allocation.frappe.db, "get_value", return_value="Co"), patch.object(
			allocation, "branch_sales", return_value=sales
		):
			return allocation.suggest_sales_share("Co", "Main - Co", "2026-01-01", "2026-03-31")

	def test_a_branch_that_sold_nothing_pays_nothing(self):
		rows = self.run_suggest({"A": 300.0, "B": 100.0, "C": 0.0})
		self.assertEqual({r["cost_center"]: r["percentage"] for r in rows}, {"A": 75.0, "B": 25.0})

	def test_when_no_branch_sold_anything_they_share_equally(self):
		rows = self.run_suggest({"A": 0.0, "B": 0.0})
		self.assertEqual([r["percentage"] for r in rows], [50.0, 50.0])

	def test_no_branch_other_than_the_main_is_an_error(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_suggest({})

	def test_a_cost_centre_of_another_company_is_refused(self):
		with patch.object(allocation.frappe, "has_permission"), patch.object(allocation.frappe.db, "get_value", return_value="Other Co"):
			with self.assertRaises(frappe.ValidationError):
				allocation.suggest_sales_share("Co", "Main - Other", "2026-01-01", "2026-03-31")


class TestMake(unittest.TestCase):
	def test_a_second_allocation_for_the_same_day_is_refused(self):
		with patch.object(allocation.frappe, "has_permission"), patch.object(allocation.frappe.db, "get_value", return_value="Co"), patch.object(
			allocation.frappe.db, "exists", return_value="CCA-1"
		), patch.object(allocation, "suggest_sales_share") as suggest:
			with self.assertRaises(frappe.ValidationError):
				allocation.make_allocation("Main - Co", "2026-12-01", "2026-01-01", "2026-03-31")
		suggest.assert_not_called()


class TestAgainstTheBooks(unittest.TestCase):
	def test_the_sales_the_suggestion_uses_are_the_invoice_lines(self):
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		sales = allocation.branch_sales(company, "2000-01-01", "2100-01-01")
		for cost_center, net in sales.items():
			expected = frappe.db.sql(
				"""select ifnull(sum(i.base_net_amount), 0) from `tabSales Invoice Item` i join `tabSales Invoice` s on s.name = i.parent
				where s.docstatus = 1 and s.company = %s and i.cost_center = %s""",
				(company, cost_center),
			)[0][0]
			self.assertAlmostEqual(net, float(expected), places=2)

	def test_the_endpoint_that_creates_a_document_is_post_only(self):
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[allocation.make_allocation], ["POST"])
