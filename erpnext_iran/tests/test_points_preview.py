import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import loyalty


class TestPointsPreview(unittest.TestCase):
	def run_preview(self, amount, program="hamid", collection_factor=10000):
		with patch.object(loyalty.frappe, "has_permission"), patch.object(
			loyalty.frappe.db, "get_value", return_value=program
		), patch(
			"erpnext.accounts.doctype.loyalty_program.loyalty_program.get_loyalty_program_details_with_points",
			return_value=frappe._dict(collection_factor=collection_factor, tier_name="Silver"),
		) as details:
			result = loyalty.points_preview("C", "Co", amount)
		self.details = details
		return result

	def test_points_are_whole_units_of_the_collection_factor(self):
		self.assertEqual(self.run_preview(75000)["points"], 7)
		self.assertEqual(self.run_preview(9999)["points"], 0)
		self.assertEqual(self.run_preview(100000)["points"], 10)

	def test_a_customer_outside_any_programme_is_not_enrolled(self):
		self.assertEqual(self.run_preview(100000, program=None), {"points": 0, "tier": None, "enrolled": 0})

	def test_a_negative_amount_earns_nothing(self):
		self.assertEqual(self.run_preview(-5)["points"], 0)

	def test_the_tier_is_passed_on(self):
		self.assertEqual(self.run_preview(50000)["tier"], "Silver")

	def test_the_programme_is_handed_to_erpnext(self):
		# ERPNext's function fails with "Loyalty Program None not found" when it is not given the programme
		self.run_preview(50000)
		self.assertEqual(self.details.call_args.kwargs["loyalty_program"], "hamid")
