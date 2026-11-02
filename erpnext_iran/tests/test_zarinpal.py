import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_iran import zarinpal


class Settings(dict):
	def __getattr__(self, name):
		return self.get(name)


class FakeLog:
	def __init__(self, data=None, reference=("Payment Request", "ACC-PRQ-1")):
		self.data = json.dumps(data or {"amount_requested": 150000})
		self.reference_doctype, self.reference_docname = reference
		self.db_set = MagicMock()


class TestZarinpal(unittest.TestCase):
	def setUp(self):
		for patcher in (
			patch.object(zarinpal.frappe, "_", side_effect=lambda text: text),
			patch.object(zarinpal.frappe, "throw", side_effect=frappe.ValidationError),
			patch.object(zarinpal.frappe, "db", new=MagicMock()),
			patch.object(zarinpal.frappe, "log_error"),
			patch.object(zarinpal, "get_url", side_effect=lambda path="": f"https://site.test{path}"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_only_rial_and_toman_are_accepted(self):
		zarinpal.validate_currency("IRR")
		zarinpal.validate_currency("IRT")
		with self.assertRaises(frappe.ValidationError):
			zarinpal.validate_currency("USD")

	def test_the_sandbox_has_to_be_asked_for_outside_developer_mode(self):
		with patch.object(zarinpal.frappe, "conf", frappe._dict(developer_mode=0)):
			with self.assertRaises(frappe.ValidationError):
				zarinpal.api_urls(Settings(live_mode=0, allow_sandbox=0))
			self.assertEqual(zarinpal.api_urls(Settings(live_mode=0, allow_sandbox=1))[0], zarinpal.SANDBOX_API)
			self.assertEqual(zarinpal.api_urls(Settings(live_mode=1))[0], zarinpal.LIVE_API)

	def test_a_payment_is_started_and_the_customer_sent_to_zarinpal(self):
		log = MagicMock(data="{}")
		settings = Settings(live_mode=1, merchant_id="m" * 36)
		with (
			patch("frappe.integrations.utils.create_request_log", return_value=log),
			patch.object(zarinpal, "_post", return_value={"data": {"code": 100, "authority": "A0001"}}) as post,
		):
			url = zarinpal.get_payment_url(
				settings, amount=150000.0, currency="IRT", payer_email="a@b.ir", description="Invoice", order_id="PRQ-1"
			)

		self.assertEqual(url, f"{zarinpal.LIVE_START_PAY}/A0001")
		endpoint, payload = post.call_args.args
		self.assertTrue(endpoint.endswith("/request.json"))
		self.assertEqual(payload["amount"], 150000)
		self.assertEqual(payload["currency"], "IRT")
		self.assertEqual(payload["callback_url"], "https://site.test/api/method/erpnext_iran.zarinpal.callback")
		saved = log.db_set.call_args_list[-1].args[0]
		self.assertEqual(saved["request_id"], "A0001")
		self.assertEqual(json.loads(saved["data"])["amount_requested"], 150000)

	def test_a_refused_request_is_a_failed_payment(self):
		log = MagicMock(data="{}")
		with (
			patch("frappe.integrations.utils.create_request_log", return_value=log),
			patch.object(zarinpal, "_post", return_value={"errors": {"code": -9}}),
		):
			with self.assertRaises(frappe.ValidationError):
				zarinpal.get_payment_url(
					Settings(live_mode=1, merchant_id="m"), amount=1000, currency="IRT", order_id="PRQ-1"
				)
		self.assertEqual(log.db_set.call_args.args[0]["status"], "Failed")

	def confirm(self, status, verified, log=None):
		log = log or FakeLog()
		reference = MagicMock()
		with (
			patch.object(zarinpal, "_lock_queued_request", return_value=log),
			patch.object(zarinpal.frappe, "get_single", return_value=Settings(live_mode=1, merchant_id="m")),
			patch.object(zarinpal.frappe, "get_doc", return_value=reference),
			patch.object(zarinpal.frappe, "flags", frappe._dict()),
			patch.object(zarinpal, "_verify", return_value=verified) as verify,
		):
			result = zarinpal.confirm_payment("A0001", status)
		return result, log, reference, verify

	def test_a_verified_payment_tells_the_payment_request(self):
		result, log, reference, verify = self.confirm("OK", True)

		self.assertEqual(result, ("success", "Payment Request", "ACC-PRQ-1"))
		verify.assert_called_once()
		self.assertEqual(verify.call_args.args[2], 150000)  # the amount that was asked, not one from the callback
		log.db_set.assert_called_with("status", "Completed")
		reference.run_method.assert_called_once_with("on_payment_authorized", "Completed")

	def test_a_payment_zarinpal_does_not_verify_is_failed(self):
		result, log, reference, _verify = self.confirm("OK", False)

		self.assertEqual(result[0], "failed")
		log.db_set.assert_called_with("status", "Failed")
		reference.run_method.assert_not_called()

	def test_a_cancelled_payment_is_not_verified_at_all(self):
		result, log, reference, verify = self.confirm("NOK", True)

		self.assertEqual(result[0], "failed")
		log.db_set.assert_called_with("status", "Cancelled")
		verify.assert_not_called()
		reference.run_method.assert_not_called()

	def test_a_second_callback_of_a_done_payment_does_not_apply_it_again(self):
		with (
			patch.object(zarinpal, "_lock_queued_request", return_value=None),
			patch.object(zarinpal.frappe, "db", new=MagicMock()) as db,
		):
			db.get_value.return_value = ("Payment Request", "ACC-PRQ-1")
			self.assertEqual(zarinpal.confirm_payment("A0001", "OK"), ("success", "Payment Request", "ACC-PRQ-1"))
			db.get_value.return_value = None
			self.assertEqual(zarinpal.confirm_payment("unknown", "OK")[0], "failed")

	def test_an_unreachable_gateway_gives_an_empty_answer(self):
		import requests

		with patch.object(zarinpal.requests, "post", side_effect=requests.ConnectionError):
			self.assertEqual(zarinpal._post("https://x", {}), {})
