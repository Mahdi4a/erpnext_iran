from unittest.mock import patch

import frappe
import unittest

from erpnext_iran.loyalty import max_redeem_percent, validate_redeem_limit

SETTING = "iran_base.settings.get_setting"


def invoice(total=100000, loyalty=0, redeem=1):
	return frappe._dict(grand_total=total, rounded_total=total, loyalty_amount=loyalty, redeem_loyalty_points=redeem)


class TestRedeemLimit(unittest.TestCase):
	def test_no_limit_by_default(self):
		for value in (None, 0, 100):
			with patch(SETTING, return_value=value):
				self.assertEqual(max_redeem_percent(), 100)
				validate_redeem_limit(invoice(loyalty=100000))

	def test_within_the_limit_passes(self):
		with patch(SETTING, return_value=30):
			validate_redeem_limit(invoice(loyalty=30000))

	def test_over_the_limit_is_refused(self):
		with patch(SETTING, return_value=30):
			with self.assertRaises(frappe.ValidationError):
				validate_redeem_limit(invoice(loyalty=31000))

	def test_invoice_without_redeeming_is_not_checked(self):
		with patch(SETTING, return_value=30):
			validate_redeem_limit(invoice(loyalty=90000, redeem=0))
			validate_redeem_limit(invoice(loyalty=0))
