"""Snapp Pay (اسنپ‌پی): installments, as a payment gateway for ERPNext's Payment Request.

The calls follow the code of a published Snapp Pay integration, not an official document, so check the
amounts' unit and the field names against the sandbox Snapp Pay gives you before going live. The base URL is
the one in your contract.

1. POST /api/online/v1/oauth/token (Basic client id:secret) grant_type=password scope=online-merchant
2. GET  /api/online/offer/v1/eligible?amount=                -> response.eligible
3. POST /api/online/payment/v1/token {transactionId, amount, returnURL, mobile, cartList, ...}
                                                              -> response.paymentToken, response.paymentPageUrl
4. the customer pays at paymentPageUrl and comes back to returnURL
5. POST /api/online/payment/v1/verify {paymentToken}, then /settle; /revert when settling fails
Every answer is {successful, response, errorData}.
"""

from __future__ import annotations

import hashlib
import json

import frappe
import requests
from frappe import _

from erpnext_iran import gateways

SERVICE = "Snapp Pay"
TIMEOUT = 20
CALLBACK_METHOD = "erpnext_iran.snapppay.callback"
TOKEN_KEY = "iran_snapppay_token"


def validate_currency(currency):
	gateways.validate_currency(currency, "Snapp Pay")


def base(settings) -> str:
	if not settings.api_url:
		frappe.throw(_("Snapp Pay is not configured. Set the API Address from your contract in Snapp Pay Settings."))
	return settings.api_url.rstrip("/")


def _request(method: str, url: str, **kwargs) -> dict:
	try:
		response = requests.request(method, url, timeout=TIMEOUT, **kwargs)
		return response.json()
	except (requests.RequestException, ValueError):
		return {}


def access_token(settings, refresh: bool = False) -> str:
	if not refresh and (cached := frappe.cache.get_value(TOKEN_KEY)):
		return cached
	secret = settings.get_password("client_secret", raise_exception=False)
	if not (settings.client_id and secret and settings.username and settings.get_password("password", raise_exception=False)):
		frappe.throw(_("Snapp Pay is not configured. Fill the keys in Snapp Pay Settings."))
	body = _request(
		"POST",
		f"{base(settings)}/api/online/v1/oauth/token",
		auth=(settings.client_id, secret),
		data={"grant_type": "password", "scope": "online-merchant", "username": settings.username, "password": settings.get_password("password")},
	)
	token = body.get("access_token")
	if not token:
		frappe.log_error(f"Snapp Pay login failed: {body}", "Snapp Pay Error")
		frappe.throw(_("Could not connect to Snapp Pay. Check the keys in Snapp Pay Settings."))
	frappe.cache.set_value(TOKEN_KEY, token, expires_in_sec=max(int(body.get("expires_in") or 60) - 10, 10))
	return token


def call(settings, method: str, path: str, **kwargs) -> dict:
	"""An authorised call. A rejected token is replaced once (the cached one may have expired early)."""
	for attempt in range(2):
		headers = {"Authorization": f"Bearer {access_token(settings, refresh=bool(attempt))}"}
		body = _request(method, f"{base(settings)}{path}", headers=headers, **kwargs)
		if body.get("successful") or (body.get("errorData") or {}).get("errorCode") not in ("401", "UNAUTHORIZED"):
			break
	return body


def eligible(settings, amount: int) -> dict:
	body = call(settings, "GET", f"/api/online/offer/v1/eligible?amount={amount}")
	return (body.get("response") or {}) if body.get("successful") else {}


def get_payment_url(settings, **kwargs) -> str:
	from frappe.integrations.utils import create_request_log

	currency = kwargs.get("currency")
	validate_currency(currency)
	amount = gateways.to_unit(kwargs.get("amount"), currency, settings.amount_unit)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero"))
	mobile = gateways.mobile_for(kwargs)
	if not mobile:
		frappe.throw(_("Snapp Pay needs the customer's mobile number. Add it to the customer."))

	offer = eligible(settings, amount)
	if not offer.get("eligible"):
		frappe.throw(offer.get("description") or _("Snapp Pay installments are not available for this amount."))

	request_log = create_request_log(kwargs, service_name=SERVICE)
	name = kwargs.get("description") or kwargs.get("title") or _("Order")
	cart_id = int(hashlib.sha1(request_log.name.encode()).hexdigest()[:7], 16)
	body = call(
		settings,
		"POST",
		"/api/online/payment/v1/token",
		json={
			"transactionId": request_log.name,
			"amount": amount,
			"returnURL": gateways.callback_url(CALLBACK_METHOD, request_log.name),
			"paymentMethodTypeDto": "INSTALLMENT",
			"mobile": mobile,
			"discountAmount": 0,
			"externalSourceAmount": 0,
			"cartList": [
				{
					"cartId": cart_id,
					"cartItems": [{"id": 1, "name": str(name)[:100], "count": 1, "amount": amount, "category": "general"}],
					"totalAmount": amount,
					"isShipmentIncluded": False,
					"shippingAmount": 0,
					"isTaxIncluded": True,
					"taxAmount": 0,
				}
			],
		},
	)
	response = body.get("response") or {}
	if not (body.get("successful") and response.get("paymentToken") and response.get("paymentPageUrl")):
		request_log.db_set({"status": "Failed", "error": json.dumps(body)[:1000]})
		frappe.log_error(f"Snapp Pay token failed: {body}", "Snapp Pay Error")
		frappe.throw((body.get("errorData") or {}).get("message") or _("Could not start the payment. Please try again later."))

	request_log.db_set({"request_id": response["paymentToken"], "status": "Queued", "data": json.dumps({**json.loads(request_log.data or "{}"), "amount_requested": amount, "currency": currency})})
	frappe.db.commit()
	return response["paymentPageUrl"]


def settle(settings, payment_token: str) -> bool:
	"""verify, then settle; a payment that cannot be settled is given back (revert)."""
	if not call(settings, "POST", "/api/online/payment/v1/verify", json={"paymentToken": payment_token}).get("successful"):
		return False
	if call(settings, "POST", "/api/online/payment/v1/settle", json={"paymentToken": payment_token}).get("successful"):
		return True
	call(settings, "POST", "/api/online/payment/v1/revert", json={"paymentToken": payment_token})
	return False


def confirm_payment(request: str):
	log = gateways.lock_queued(request, SERVICE)
	if log is None:
		done = gateways.already_done(request, SERVICE)
		return ("success", *done) if done else ("failed", None, None)
	reference = gateways.reference_of(log)
	if not log.request_id or not settle(frappe.get_single("Snapp Pay Settings"), log.request_id):
		log.db_set("status", "Failed")
		frappe.db.commit()
		return ("failed", *reference)
	return ("success", *gateways.complete(log, SERVICE))


@frappe.whitelist(allow_guest=True)
def callback(request: str | None = None):
	"""Where Snapp Pay sends the customer back to. Whatever the query says, the payment is asked about."""
	outcome, doctype, docname = confirm_payment(request or "")
	gateways.redirect_to_result(outcome, doctype, docname)
