import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_iran import gateways, snapppay, tara


def settings(**extra):
	return frappe._dict(
		{
			"api_url": "https://gw.example", "username": "u", "service_id": "S1", "amount_unit": "Rial", "client_id": "cid",
			**extra,
		},
		get_password=lambda key, raise_exception=True: {"password": "pw", "client_secret": "sec"}.get(key),
	)


def kwargs(**extra):
	return {"amount": 500000, "currency": "IRR", "mobile": "0912 111 2233", "description": "Invoice 1", "order_id": "ACC-1", "reference_doctype": "Payment Request", "reference_docname": "PR-1", **extra}


class TestUnits(unittest.TestCase):
	def test_amounts_follow_the_gateway_unit(self):
		self.assertEqual(gateways.to_unit(1000, "IRR", "Rial"), 1000)
		self.assertEqual(gateways.to_unit(1000, "IRT", "Rial"), 10000)
		self.assertEqual(gateways.to_unit(1000, "IRR", "Toman"), 100)
		self.assertEqual(gateways.to_unit(1000, "IRT", "Toman"), 1000)
		self.assertEqual(gateways.to_unit(None, "IRR", "Rial"), 0)

	def test_only_rials_and_tomans(self):
		gateways.validate_currency("IRR", "X")
		gateways.validate_currency("IRT", "X")
		with self.assertRaises(frappe.ValidationError):
			gateways.validate_currency("USD", "X")


class TestTara(unittest.TestCase):
	def start(self, posts):
		log = MagicMock()
		log.name = "REQ1"
		log.data = "{}"
		calls = []

		def post(s, path, payload, token=None):
			calls.append((path, payload, token))
			return posts[path]

		with patch("frappe.integrations.utils.create_request_log", return_value=log), patch.object(tara, "_post", side_effect=post), patch.object(
			tara.frappe.db, "commit"
		):
			try:
				url = tara.get_payment_url(settings(), **kwargs())
			except frappe.ValidationError:
				url = None
		return url, calls, log

	def test_a_payment_logs_in_gets_a_token_and_sends_the_customer_to_the_redirect_page(self):
		url, calls, log = self.start({"/api/v2/authenticate": (200, {"accessToken": "AT"}), "/api/getToken": (200, {"token": "TT"})})
		self.assertIn("erpnext_iran.tara.redirect?request=REQ1", url)
		paths = [c[0] for c in calls]
		self.assertEqual(paths, ["/api/v2/authenticate", "/api/getToken"])
		body = calls[1][1]
		self.assertEqual((body["amount"], body["mobile"], body["serviceAmountList"]), (500000, "09121112233", [{"serviceId": "S1", "amount": 500000}]))
		self.assertIn("request=REQ1", body["callBackUrl"])
		self.assertEqual(calls[1][2], "AT")
		self.assertEqual(log.db_set.call_args.args[0]["request_id"], "TT")

	def test_a_failed_login_or_token_is_an_error_not_a_url(self):
		self.assertIsNone(self.start({"/api/v2/authenticate": (401, {})})[0])
		self.assertIsNone(self.start({"/api/v2/authenticate": (200, {"accessToken": "AT"}), "/api/getToken": (500, {})})[0])

	def test_verify_needs_result_zero_and_a_reference_number(self):
		def verify(body, status=200):
			with patch.object(tara, "authenticate", return_value="AT"), patch.object(tara, "_post", return_value=(status, body)):
				return tara.verify(settings(), "TT")

		self.assertTrue(verify({"result": 0, "rrn": "123"}))
		self.assertFalse(verify({"result": 0, "rrn": ""}))
		self.assertFalse(verify({"result": 5, "rrn": "123"}))
		self.assertFalse(verify({}))
		self.assertFalse(verify({"result": 0, "rrn": "1"}, status=500))

	def test_verify_logs_in_again_after_a_401(self):
		answers = iter([(401, {}), (200, {"result": 0, "rrn": "9"})])
		with patch.object(tara, "authenticate", return_value="AT") as login, patch.object(tara, "_post", side_effect=lambda *a, **k: next(answers)):
			self.assertTrue(tara.verify(settings(), "TT"))
		self.assertEqual(login.call_count, 2)

	def confirm(self, token, result, verified=True, log=True):
		fake = MagicMock(request_id="TT", reference_doctype="Payment Request", reference_docname="PR-1", data="{}") if log else None
		with patch.object(gateways, "lock_queued", return_value=fake), patch.object(tara, "verify", return_value=verified), patch.object(
			tara.frappe, "get_single", return_value=settings()
		), patch.object(gateways, "complete", return_value=("Payment Request", "PR-1")) as complete, patch.object(
			gateways, "already_done", return_value=None
		), patch.object(tara.frappe.db, "commit"):
			return tara.confirm_payment("REQ1", token, result, "ref"), fake, complete

	def test_a_paid_return_completes_once_verified(self):
		(outcome, *_), _log, complete = self.confirm("TT", "0")
		self.assertEqual(outcome, "success")
		complete.assert_called_once()

	def test_failures_never_complete(self):
		for token, result, verified in (("TT", "1", True), ("OTHER", "0", True), ("TT", "0", False), (None, None, True)):
			(outcome, *_), log, complete = self.confirm(token, result, verified)
			self.assertEqual(outcome, "failed", (token, result, verified))
			complete.assert_not_called()

	def test_a_return_with_a_foreign_token_leaves_the_request_waiting(self):
		(outcome, *_), log, complete = self.confirm("OTHER", "0")
		self.assertEqual(outcome, "failed")
		log.db_set.assert_not_called()  # the real payment that follows must still be accepted
		complete.assert_not_called()

	def test_a_request_that_is_not_waiting_is_failed_not_applied_twice(self):
		(outcome, *_), _log, complete = self.confirm("TT", "0", log=False)
		self.assertEqual(outcome, "failed")
		complete.assert_not_called()


class TestSnappPay(unittest.TestCase):
	def start(self, answers):
		log = MagicMock()
		log.name = "REQ2"
		log.data = "{}"
		sent = []

		def call(s, method, path, **kw):
			sent.append((method, path, kw))
			return answers[path]

		with patch("frappe.integrations.utils.create_request_log", return_value=log), patch.object(snapppay, "call", side_effect=call), patch.object(
			snapppay.frappe.db, "commit"
		):
			try:
				url = snapppay.get_payment_url(settings(), **kwargs())
			except frappe.ValidationError:
				url = None
		return url, sent, log

	ELIGIBLE = "/api/online/offer/v1/eligible?amount=500000"
	TOKEN = "/api/online/payment/v1/token"

	def test_a_payment_checks_the_offer_then_gets_a_token_and_returns_snapps_page(self):
		url, sent, log = self.start(
			{self.ELIGIBLE: {"successful": True, "response": {"eligible": True}}, self.TOKEN: {"successful": True, "response": {"paymentToken": "PT", "paymentPageUrl": "https://pay.snapp/x"}}}
		)
		self.assertEqual(url, "https://pay.snapp/x")
		body = sent[1][2]["json"]
		self.assertEqual((body["amount"], body["mobile"], body["transactionId"], body["paymentMethodTypeDto"]), (500000, "09121112233", "REQ2", "INSTALLMENT"))
		self.assertEqual(body["cartList"][0]["totalAmount"], 500000)
		self.assertIn("request=REQ2", body["returnURL"])
		self.assertEqual(log.db_set.call_args.args[0]["request_id"], "PT")

	def test_an_amount_that_is_not_eligible_is_refused_with_the_reason(self):
		url, sent, _ = self.start({self.ELIGIBLE: {"successful": True, "response": {"eligible": False, "description": "too small"}}})
		self.assertIsNone(url)
		self.assertEqual(len(sent), 1)

	def test_a_failed_token_is_an_error(self):
		url, *_ = self.start({self.ELIGIBLE: {"successful": True, "response": {"eligible": True}}, self.TOKEN: {"successful": False, "errorData": {"message": "no"}}})
		self.assertIsNone(url)

	def settle(self, verify, settle, revert=True):
		answers = {"/api/online/payment/v1/verify": {"successful": verify}, "/api/online/payment/v1/settle": {"successful": settle}, "/api/online/payment/v1/revert": {"successful": revert}}
		calls = []
		with patch.object(snapppay, "call", side_effect=lambda s, m, path, **kw: calls.append(path) or answers[path]):
			return snapppay.settle(settings(), "PT"), [p.rsplit("/", 1)[1] for p in calls]

	def test_verify_then_settle(self):
		self.assertEqual(self.settle(True, True), (True, ["verify", "settle"]))

	def test_a_payment_that_does_not_verify_stops_there(self):
		self.assertEqual(self.settle(False, True), (False, ["verify"]))

	def test_a_payment_that_cannot_be_settled_is_given_back(self):
		self.assertEqual(self.settle(True, False), (False, ["verify", "settle", "revert"]))

	def test_confirm_does_not_complete_a_failed_settlement(self):
		fake = MagicMock(request_id="PT", reference_doctype="Payment Request", reference_docname="PR-1", data="{}")
		with patch.object(gateways, "lock_queued", return_value=fake), patch.object(snapppay, "settle", return_value=False), patch.object(
			snapppay.frappe, "get_single", return_value=settings()
		), patch.object(gateways, "complete") as complete, patch.object(snapppay.frappe.db, "commit"):
			self.assertEqual(snapppay.confirm_payment("REQ2")[0], "failed")
		complete.assert_not_called()
		fake.db_set.assert_called_with("status", "Failed")
