"""What the Iranian payment gateways of this app (Zarinpal, Tara, Snapp Pay) share.

They all work the same way for ERPNext's Payment Request: the controller starts a payment and returns a
page for the customer, the customer pays there and comes back to a guest callback, which asks the gateway
whether the payment really happened and only then marks the request paid. The Integration Request holds the
state, locked while it is being settled, so a payment can never be confirmed twice."""

from __future__ import annotations

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import get_url

from erpnext_iran.zarinpal import apply_payment

CURRENCIES = ("IRR", "IRT")


def validate_currency(currency: str, name: str):
	if currency not in CURRENCIES:
		frappe.throw(_("Please select another payment method. {0} does not support transactions in currency '{1}'").format(name, currency))


def to_unit(amount, currency: str, unit: str) -> int:
	"""The amount the gateway wants: whole rials or whole tomans, whatever the invoice is in."""
	value = float(amount or 0)
	if currency == "IRT" and unit != "Toman":
		value *= 10
	elif currency == "IRR" and unit == "Toman":
		value /= 10
	return int(round(value))


def callback_url(method: str, request_name: str) -> str:
	return get_url(f"/api/method/{method}?{urlencode({'request': request_name})}")


def mobile_for(kwargs: dict) -> str | None:
	"""The payer's mobile: given, or the customer of the Payment Request."""
	from iran_base.utils.sms import try_normalize_mobile

	if mobile := try_normalize_mobile(kwargs.get("mobile") or kwargs.get("mobile_no")):
		return mobile
	doctype, name = kwargs.get("reference_doctype"), kwargs.get("reference_docname")
	if doctype == "Payment Request" and name:
		party_type, party = frappe.db.get_value("Payment Request", name, ["party_type", "party"]) or (None, None)
		if party_type == "Customer" and party:
			return try_normalize_mobile(frappe.db.get_value("Customer", party, "mobile_no"))
	return None


def lock_queued(request_name: str, service: str):
	"""The Integration Request of the payment, locked, only while it still waits. Two callbacks of one
	payment cannot both get it."""
	if not request_name or not frappe.db.exists("Integration Request", {"name": request_name, "integration_request_service": service}):
		return None
	status = frappe.db.get_value("Integration Request", request_name, "status", for_update=True)
	return frappe.get_doc("Integration Request", request_name) if status == "Queued" else None


def reference_of(log) -> tuple:
	data = frappe.parse_json(log.data or "{}")
	return (log.reference_doctype or data.get("reference_doctype"), log.reference_docname or data.get("reference_docname"))


def already_done(request_name: str, service: str):
	return frappe.db.get_value(
		"Integration Request",
		{"name": request_name, "integration_request_service": service, "status": "Completed"},
		["reference_doctype", "reference_docname"],
	)


def complete(log, service: str):
	"""The payment is verified: close the request and pay the document."""
	log.db_set("status", "Completed")
	frappe.db.commit()
	reference = reference_of(log)
	if all(reference):
		try:
			frappe.flags.data = frappe.parse_json(log.data or "{}")
			apply_payment(frappe.get_doc(*reference))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{service} payment not applied")
	return reference


def redirect_to_result(outcome: str, doctype=None, docname=None):
	page = "payment-success" if outcome == "success" else "payment-failed"
	query = f"?{urlencode({'doctype': doctype, 'docname': docname})}" if doctype and docname and outcome == "success" else ""
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = get_url(f"/{page}{query}")


def ensure_gateway(name: str, settings_doctype: str):
	"""Registers a Payment Gateway, when the payments app is installed."""
	if not frappe.db.exists("DocType", "Payment Gateway") or frappe.db.exists("Payment Gateway", name):
		return
	frappe.get_doc({"doctype": "Payment Gateway", "gateway": name, "gateway_settings": settings_doctype}).insert(ignore_permissions=True)
