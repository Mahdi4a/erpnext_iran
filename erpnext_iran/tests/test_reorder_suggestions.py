import unittest

import frappe

from erpnext_iran.erpnext_iran.report.reorder_suggestions import reorder_suggestions as report
from erpnext_iran.erpnext_iran.report.reorder_suggestions.reorder_suggestions import suggest


class TestSuggest(unittest.TestCase):
	def test_what_to_order_covers_the_delivery_and_the_reserve(self):
		# 60 sold in 30 days = 2 a day; 3 days delivery + 2 reserve = 10 needed; 4 in stock -> order 6
		result = suggest(stock=4, sold=60, sales_days=30, lead_days=3, safety_days=2)
		self.assertAlmostEqual(result["per_day"], 2)
		self.assertAlmostEqual(result["cover_days"], 2)
		self.assertEqual(result["to_order"], 6)

	def test_enough_stock_orders_nothing(self):
		self.assertEqual(suggest(stock=50, sold=60, sales_days=30, lead_days=3, safety_days=2)["to_order"], 0)

	def test_the_quantity_is_rounded_up_to_a_whole_unit(self):
		self.assertEqual(suggest(stock=0, sold=10, sales_days=30, lead_days=3, safety_days=0)["to_order"], 1)  # 0.99

	def test_negative_stock_counts_as_none(self):
		result = suggest(stock=-5, sold=30, sales_days=30, lead_days=2, safety_days=0)
		self.assertEqual(result["to_order"], 2)
		self.assertEqual(result["cover_days"], 0)

	def test_an_item_that_did_not_sell_is_left_out(self):
		self.assertIsNone(suggest(stock=0, sold=0, sales_days=30, lead_days=3, safety_days=2))
		self.assertIsNone(suggest(stock=10, sold=-3, sales_days=30, lead_days=3, safety_days=2))  # returns beat sales


class TestReport(unittest.TestCase):
	def filters(self, **extra):
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		return {"company": company, "sales_days": 3650, "lead_days": 3, "safety_days": 2, "only_needed": 0, **extra}

	def test_sold_is_what_the_invoices_say(self):
		rows = report.execute(self.filters())[1]
		for row in rows:
			expected = frappe.db.sql(
				"""select sum(i.stock_qty) from `tabSales Invoice Item` i join `tabSales Invoice` s on s.name = i.parent
				where s.docstatus = 1 and s.update_stock = 1 and i.warehouse = %s and i.item_code = %s""",
				(row["warehouse"], row["item_code"]),
			)[0][0]
			self.assertAlmostEqual(row["sold"], float(expected), places=3)

	def test_only_needed_hides_what_is_covered(self):
		all_rows = report.execute(self.filters())[1]
		needed = report.execute(self.filters(only_needed=1))[1]
		self.assertTrue(all(r["to_order"] > 0 for r in needed))
		self.assertLessEqual(len(needed), len(all_rows))

	def test_the_most_urgent_item_comes_first(self):
		covers = [r["cover_days"] for r in report.execute(self.filters())[1]]
		self.assertEqual(covers, sorted(covers))

	def test_bad_periods_are_refused(self):
		for bad in ({"sales_days": 0}, {"sales_days": -5}, {"lead_days": -1}, {"safety_days": -1}):
			with self.assertRaises(frappe.ValidationError):
				report.execute(self.filters(**bad))

	def test_the_request_endpoint_is_post_only_and_refuses_empty_or_foreign_rows(self):
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[report.make_material_request], ["POST"])
		company = self.filters()["company"]
		with self.assertRaises(frappe.ValidationError):
			report.make_material_request(company, "[]")
		with self.assertRaises(frappe.ValidationError):
			report.make_material_request(company, '[{"item_code": "X", "warehouse": "W", "to_order": 0}]')
