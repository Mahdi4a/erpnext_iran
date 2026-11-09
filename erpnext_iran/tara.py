"""Tara (تارا, tara360.ir): buy now, pay later, as a payment gateway for ERPNext's Payment Request.

The calls follow the code of Tara's own published WooCommerce plugin, not an official document, so check the
amounts' unit and the field names against the sandbox Tara gives you before going live.

1. POST /api/v2/authenticate {username, password}           -> body.accessToken
2. POST /api/getToken (Bearer) {amount, mobile, callBackUrl, ...} -> body.token
3. the customer's browser POSTs {username, token} to /api/ipgPurchase and pays in the Tara app
4. Tara POSTs {token, result, channelRefNumber} to callBackUrl; result "0" means paid
5. POST /api/purchaseVerify (Bearer) {token, ip}            -> body.result == 0 and body.rrn
"""

from __future__ import annotations

import json
from html import escape

import frappe
import requests
from frappe import _
from frappe.utils import cint

from erpnext_iran import gateways

SERVICE = "Tara"
TIMEOUT = 15
CALLBACK_METHOD = "erpnext_iran.tara.callback"
REDIRECT_METHOD = "erpnext_iran.tara.redirect"
ITEM_UNIT = 5  # the unit code Tara's own plugin sends for an invoice line


def validate_currency(currency):
	gateways.validate_currency(currency, "Tara")


def base(settings) -> str:
	return (settings.api_url or "https://pay.tara360.ir/pay").rstrip("/")


def _post(settings, path: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
	headers = {"Content-Type": "application/json"}
	if token:
		headers["Authorization"] = f"Bearer {token}"
	try:
		response = requests.post(f"{base(settings)}{path}", json=payload, headers=headers, timeout=TIMEOUT)
		try:
			return response.status_code, response.json()
		except ValueError:
			return response.status_code, {}
	except requests.RequestException:
		return 0, {}


def authenticate(settings) -> str:
	if not (settings.username and settings.get_password("password", raise_exception=False)):
		frappe.throw(_("Tara is not configured. Set the user name and password in Tara Settings."))
	status, body = _post(settings, "/api/v2/authenticate", {"username": settings.username, "password": settings.get_password("password")})
	token = body.get("accessToken") if status == 200 else None
	if not token:
		frappe.log_error(f"Tara authenticate failed: {status} {body}", "Tara Error")
		frappe.throw(_("Could not connect to Tara. Check the user name and password in Tara Settings."))
	return token


def get_payment_url(settings, **kwargs) -> str:
	from frappe.integrations.utils import create_request_log

	currency = kwargs.get("currency")
	validate_currency(currency)
	amount = gateways.to_unit(kwargs.get("amount"), currency, settings.amount_unit)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))
	mobile = gateways.mobile_for(kwargs)
	if not mobile:
		frappe.throw(_("Tara needs the customer's mobile number. Add it to the customer."))
	if not settings.service_id:
		frappe.throw(_("Set the Gateway Code in Tara Settings."))

	request_log = create_request_log(kwargs, service_name=SERVICE)
	description = kwargs.get("description") or kwargs.get("title") or kwargs.get("order_id") or ""
	status, body = _post(
		settings,
		"/api/getToken",
		{
			"additionalData": description,
			"mobile": mobile,
			"callBackUrl": gateways.callback_url(CALLBACK_METHOD, request_log.name),
			"amount": amount,
			"vat": 0,
			"serviceAmountList": [{"serviceId": settings.service_id, "amount": amount}],
			"taraInvoiceItemList": [
				{"name": description or _("Order"), "code": str(kwargs.get("order_id") or request_log.name)[:30], "count": 1, "unit": ITEM_UNIT, "fee": amount, "data": ""}
			],
			"ip": frappe.local.request_ip or "127.0.0.1",
		},
		token=authenticate(settings),
	)
	token = body.get("token") if status == 200 else None
	if not token:
		request_log.db_set({"status": "Failed", "error": json.dumps(body)[:1000]})
		frappe.log_error(f"Tara getToken failed: {status} {body}", "Tara Error")
		frappe.throw(_("Could not start the payment. Please try again later."))

	request_log.db_set({"request_id": token, "status": "Queued", "data": json.dumps({**json.loads(request_log.data or "{}"), "amount_requested": amount, "currency": currency})})
	frappe.db.commit()
	return frappe.utils.get_url(f"/api/method/{REDIRECT_METHOD}?request={request_log.name}")


@frappe.whitelist(allow_guest=True)
def redirect(request: str | None = None):
	"""Tara wants the customer's browser to POST to it, so the payment URL is this page that does it."""
	settings = frappe.get_single("Tara Settings")
	log = gateways.lock_queued(request or "", SERVICE)
	if log is None or not log.request_id:
		frappe.respond_as_web_page(_("Payment"), _("This payment link is not valid any more."), http_status_code=404)
		return
	form = (
		f'<form id="tara" method="POST" action="{escape(base(settings))}/api/ipgPurchase">'
		f'<input type="hidden" name="username" value="{escape(settings.username or "")}">'
		f'<input type="hidden" name="token" value="{escape(log.request_id)}">'
		f'<button type="submit" class="btn btn-primary">{escape(_("Continue to Tara"))}</button></form>'
		'<script>document.getElementById("tara").submit();</script>'
	)
	frappe.respond_as_web_page(_("Payment"), form, indicator_color="blue")


def verify(settings, token: str) -> bool:
	"""True only for a verified payment with a reference number. A rejected token (401) logs in once more."""
	for attempt in range(2):
		status, body = _post(settings, "/api/purchaseVerify", {"token": token, "ip": frappe.local.request_ip or "127.0.0.1"}, token=authenticate(settings))
		if status != 401 or attempt:
			break
	return status == 200 and cint(body.get("result", -1)) == 0 and bool(body.get("rrn"))


def confirm_payment(request: str, token: str | None, result: str | None, ref: str | None):
	log = gateways.lock_queued(request, SERVICE)
	if log is None:
		done = gateways.already_done(request, SERVICE)
		return ("success", *done) if done else ("failed", None, None)
	reference = gateways.reference_of(log)
	# The token Tara posts back must be the one it gave us for this request. A return with another token is
	# not Tara's: it fails without touching the request, so it cannot spoil the real payment that follows.
	if token and token != log.request_id:
		return ("failed", *reference)
	if str(result) != "0" or not verify(frappe.get_single("Tara Settings"), log.request_id):
		log.db_set("status", "Failed" if str(result) == "0" else "Cancelled")
		frappe.db.commit()
		return ("failed", *reference)
	return ("success", *gateways.complete(log, SERVICE))


@frappe.whitelist(allow_guest=True)
def callback(request: str | None = None, token: str | None = None, result: str | None = None, channelRefNumber: str | None = None):  # noqa: N803
	outcome, doctype, docname = confirm_payment(request or "", token, result, channelRefNumber)
	gateways.redirect_to_result(outcome, doctype, docname)
