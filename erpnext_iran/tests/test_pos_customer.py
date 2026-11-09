import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import pos_customer


class TestCustomerForMobile(unittest.TestCase):
	def test_a_bad_number_is_refused(self):
		for bad in ("", "123", "0912", "02112345678"):
			with self.assertRaises(frappe.ValidationError):
				pos_customer.customer_for_mobile(bad)

	def test_every_spelling_finds_the_same_customer(self):
		with patch.object(pos_customer, "find_customer", return_value="09121234567") as find:
			for spelling in ("09121234567", "+989121234567", "۰۹۱۲۱۲۳۴۵۶۷", "9121234567"):
				self.assertEqual(pos_customer.customer_for_mobile(spelling), {"customer": "09121234567", "created": 0})
			self.assertEqual({call.args[0] for call in find.call_args_list}, {"09121234567"})
