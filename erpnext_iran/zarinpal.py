"""Zarinpal (زرین‌پال) as a payment gateway for ERPNext's Payment Request.

Payment Request asks the gateway controller for a payment URL. The customer pays at Zarinpal and
comes back to `callback`, which verifies the payment and tells the Payment Request through
`on_payment_authorized`, as the gateways of the payments app do."""

from __future__ import annotations

import json
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.utils import cint, get_url

SANDBOX_API = "https://sandbox.zarinpal.com/pg/v4/payment"
SANDBOX_START_PAY = "https://sandbox.zarinpal.com/pg/StartPay"
LIVE_API = "https://payment.zarinpal.com/pg/v4/payment"
LIVE_START_PAY = "https://payment.zarinpal.com/pg/StartPay"
TIMEOUT = 15
SERVICE = "Zarinpal"
CURRENCIES = ("IRR", "IRT")
# Zarinpal result codes meaning the payment is verified (101 = it was verified before)
VERIFIED_CODES = (100, 101)
CALLBACK_METHOD = "erpnext_iran.zarinpal.callback"


def validate_currency(currency: str):
	if currency not in CURRENCIES:
		frappe.throw(
			_("Please select another payment method. Zarinpal does not support transactions in currency '{0}'").format(
				currency
			)
		)


def api_urls(settings) -> tuple[str, str]:
	if cint(settings.live_mode):
		return LIVE_API, LIVE_START_PAY
	# The sandbox verifies any payment, so a live site that forgot Live Mode would hand out paid
	# invoices for nothing. It has to be asked for.
	if not (frappe.conf.developer_mode or cint(settings.allow_sandbox)):
		frappe.throw(
			_("Zarinpal is in sandbox mode. Tick Live Mode in Zarinpal Settings, or tick Allow Sandbox for testing.")
		)
	return SANDBOX_API, SANDBOX_START_PAY


def merchant_id(settings) -> str:
	if not settings.merchant_id:
		frappe.throw(_("Zarinpal is not configured. Set the Merchant ID in Zarinpal Settings."))
	return settings.merchant_id


def _post(url: str, payload: dict) -> dict:
	try:
		return requests.post(url, json=payload, headers={"Accept": "application/json"}, timeout=TIMEOUT).json()
	except (requests.RequestException, ValueError):
		return {}


def get_payment_url(settings, **kwargs) -> str:
	"""Starts the payment and returns the Zarinpal page the customer pays on."""
	from frappe.integrations.utils import create_request_log

	amount = int(round(float(kwargs.get("amount") or 0)))
	currency = kwargs.get("currency")
	validate_currency(currency)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))

	api, start_pay = api_urls(settings)
	merchant = merchant_id(settings)
	request_log = create_request_log(kwargs, service_name=SERVICE)

	metadata = {"email": kwargs["payer_email"]} if kwargs.get("payer_email") else {}
	response = _post(
		f"{api}/request.json",
		{
			"merchant_id": merchant,
			"amount": amount,
			"currency": currency,
			"description": kwargs.get("description") or kwargs.get("title") or kwargs.get("order_id") or "",
			"callback_url": get_url(f"/api/method/{CALLBACK_METHOD}"),
			"metadata": metadata,
		},
	)
	data = response.get("data") or {}
	if data.get("code") != 100 or not data.get("authority"):
		request_log.db_set({"status": "Failed", "error": json.dumps(response)[:1000]})
		frappe.log_error(f"Zarinpal request failed: {response}", "Zarinpal Error")
		frappe.throw(_("Could not start the payment. Please try again later."))

	authority = data["authority"]
	request_log.db_set(
		{
			"request_id": authority,
			"status": "Queued",
			"data": json.dumps({**json.loads(request_log.data or "{}"), "amount_requested": amount, "currency": currency}),
		}
	)
	frappe.db.commit()
	return f"{start_pay}/{authority}"


def _lock_queued_request(authority: str):
	"""The Integration Request of the payment, locked, only while it is still waiting. Two callbacks
	of one payment cannot both get it, so a payment is never confirmed twice."""
	name = frappe.db.get_value("Integration Request", {"request_id": authority, "integration_request_service": SERVICE})
	if not name:
		return None
	status = frappe.db.get_value("Integration Request", name, "status", for_update=True)
	return frappe.get_doc("Integration Request", name) if status == "Queued" else None


def _verify(settings, authority: str, amount: int) -> bool:
	api, _start = api_urls(settings)
	response = _post(
		f"{api}/verify.json", {"merchant_id": merchant_id(settings), "amount": amount, "authority": authority}
	)
	return (response.get("data") or {}).get("code") in VERIFIED_CODES


def confirm_payment(authority: str, status: str) -> tuple[str, str | None, str | None]:
	"""Verifies a payment that comes back from Zarinpal. Returns the outcome (success, failed or
	already done) and the document it was for."""
	log = _lock_queued_request(authority)
	if log is None:
		done = frappe.db.get_value(
			"Integration Request",
			{"request_id": authority, "integration_request_service": SERVICE, "status": "Completed"},
			["reference_doctype", "reference_docname"],
		)
		return ("success", *done) if done else ("failed", None, None)

	data = frappe.parse_json(log.data)
	reference = (log.reference_doctype or data.get("reference_doctype"), log.reference_docname or data.get("reference_docname"))
	settings = frappe.get_single("Zarinpal Settings")

	if status != "OK" or not _verify(settings, authority, int(data.get("amount_requested") or 0)):
		log.db_set("status", "Failed" if status == "OK" else "Cancelled")
		frappe.db.commit()
		return ("failed", *reference)

	log.db_set("status", "Completed")
	frappe.db.commit()
	if all(reference):
		try:
			frappe.flags.data = data
			frappe.get_doc(*reference).run_method("on_payment_authorized", "Completed")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Zarinpal payment not applied")
	return ("success", *reference)


@frappe.whitelist(allow_guest=True)
def callback(Authority: str | None = None, Status: str | None = None):  # noqa: N803
	"""Where Zarinpal sends the customer back to."""
	outcome, doctype, docname = confirm_payment(Authority or "", Status or "")
	page = "payment-success" if outcome == "success" else "payment-failed"
	query = f"?{urlencode({'doctype': doctype, 'docname': docname})}" if doctype and docname and outcome == "success" else ""
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = get_url(f"/{page}{query}")


def ensure_payment_gateway():
	"""Registers Zarinpal as a Payment Gateway, when the payments app is installed."""
	if not frappe.db.exists("DocType", "Payment Gateway") or frappe.db.exists("Payment Gateway", "Zarinpal"):
		return
	frappe.get_doc(
		{"doctype": "Payment Gateway", "gateway": "Zarinpal", "gateway_settings": "Zarinpal Settings"}
	).insert(ignore_permissions=True)
