"""What must not be reachable the wrong way: data-changing endpoints are POST only, so a link on another site
cannot trigger them with the cashier's session."""

import unittest

import frappe

from erpnext_iran import discount, iran_payroll, jalali, moadian_send, naming, offline, pos_customer, woocommerce
from erpnext_iran.erpnext_iran.doctype.iran_cheque import iran_cheque

MUTATING = [
	pos_customer.customer_for_mobile,
	offline.submit_sales,
	discount.approve_discount,
	woocommerce.sync_now,
	iran_cheque.make_action,
	moadian_send.send_invoice,
	moadian_send.cancel_in_moadian,
	moadian_send.check_status,
	naming.add_jalali_series,
	naming.remove_jalali_series,
	jalali.create_fiscal_year,
]


class TestEndpoints(unittest.TestCase):
	def test_endpoints_that_change_data_accept_post_only(self):
		for function in MUTATING:
			with self.subTest(function.__name__):
				self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[function], ["POST"])

	def test_guest_endpoints_are_the_known_ones(self):
		"""A new allow_guest endpoint must be added here on purpose, after someone has thought about its checks."""
		allowed = {
			"erpnext_iran.channels.catalog_feed",  # secret token
			"erpnext_iran.woocommerce.webhook",  # HMAC signature
			"erpnext_iran.tara.redirect",  # unguessable request name
			"erpnext_iran.tara.callback",  # verified with the gateway
			"erpnext_iran.snapppay.callback",  # verified with the gateway
			"erpnext_iran.zarinpal.callback",  # verified with the gateway
		}
		found = set()
		import importlib
		import pathlib

		root = pathlib.Path(frappe.get_app_path("erpnext_iran"))
		for path in root.glob("*.py"):
			source = path.read_text(encoding="utf8")
			if "allow_guest=True" not in source:
				continue
			module = importlib.import_module(f"erpnext_iran.{path.stem}")
			for name in dir(module):
				function = getattr(module, name)
				if callable(function) and function in frappe.guest_methods:
					found.add(f"erpnext_iran.{path.stem}.{name}")
		self.assertEqual(found, allowed)
