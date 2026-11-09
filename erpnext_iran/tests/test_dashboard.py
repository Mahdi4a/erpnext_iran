import json
import unittest

import frappe

from erpnext_iran import dashboard


class TestDashboard(unittest.TestCase):
	def test_ensure_is_idempotent(self):
		dashboard.ensure_dashboard()
		before = (
			frappe.db.count("Number Card", {"label": ["in", [c["label"] for c in dashboard.NUMBER_CARDS]]}),
			frappe.db.count("Dashboard Chart", {"chart_name": ["in", [c["chart_name"] for c in dashboard.CHARTS]]}),
			frappe.db.count("Workspace", {"name": dashboard.WORKSPACE}),
		)
		dashboard.ensure_dashboard()
		after = (
			frappe.db.count("Number Card", {"label": ["in", [c["label"] for c in dashboard.NUMBER_CARDS]]}),
			frappe.db.count("Dashboard Chart", {"chart_name": ["in", [c["chart_name"] for c in dashboard.CHARTS]]}),
			frappe.db.count("Workspace", {"name": dashboard.WORKSPACE}),
		)
		self.assertEqual(before, after)
		self.assertEqual(after, (len(dashboard.NUMBER_CARDS), len(dashboard.CHARTS), 1))

	def test_every_dynamic_between_filter_is_one_js_expression(self):
		# Frappe evaluates the value as JS; a Python list of two strings makes the filter match nothing
		specs = dashboard.NUMBER_CARDS + dashboard.CHARTS
		for spec in specs:
			for _doctype, _field, operator, value in spec.get("dynamic", []):
				if operator == "Between":
					self.assertIsInstance(value, str, spec)
					self.assertTrue(value.startswith("[") and value.endswith("]"), spec)

	def test_filters_are_valid_json_on_the_saved_documents(self):
		dashboard.ensure_dashboard()
		for card in dashboard.NUMBER_CARDS:
			json.loads(frappe.db.get_value("Number Card", card["label"], "filters_json") or "[]")

	def test_the_low_stock_card_returns_a_plain_number(self):
		self.assertIsInstance(dashboard.low_stock_count(), int)

	def test_only_money_cards_show_the_currency(self):
		dashboard.ensure_dashboard()
		self.assertFalse(frappe.db.get_value("Number Card", "Low Stock Items", "currency"))
		self.assertFalse(frappe.db.get_value("Number Card", "Today's Invoices", "currency"))
		self.assertTrue(frappe.db.get_value("Number Card", "Today's Sales", "currency"))


class TestNewCards(unittest.TestCase):
	def test_a_card_added_later_reaches_an_existing_dashboard(self):
		dashboard.ensure_dashboard()
		workspace = frappe.get_doc("Workspace", dashboard.WORKSPACE)
		self.assertIn("Expiring Stock", {row.number_card_name for row in workspace.number_cards})
		blocks = [b for b in json.loads(workspace.content) if b["type"] == "number_card"]
		self.assertEqual(len(blocks), len(dashboard.NUMBER_CARDS))

	def test_the_expiry_card_gives_a_plain_number(self):
		self.assertIsInstance(dashboard.expiring_count(), int)
