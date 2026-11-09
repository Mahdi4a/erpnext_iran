"""WooCommerce store <-> ERPNext.

Orders: the store posts every created/updated order to `webhook` (signed with the shared secret). A paid order
becomes a submitted Sales Order, once, with the store's order id on it. Items are matched by SKU = item code.
Catalog: items marked "Sell Online" are pushed with price and stock, on the hour and right after a sale.

Prices: the store may be in tomans; `Price Factor` converts (rials = store price x factor).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import frappe
import requests
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime, nowdate

from erpnext_iran.channels import price_of, settings, stock_of

TIMEOUT = 30
BATCH = 50
PAID_STATUSES = ("processing", "completed")
CANCEL_STATUSES = ("cancelled", "refunded", "failed")
CURRENCIES = ("IRR", "IRT")
WALK_IN_ONLINE = "مشتری وب‌سایت"


class WooError(Exception):
	pass


# ----------------------------------------------------------------------------- orders


def signature_ok(body: bytes, signature: str | None, secret: str | None) -> bool:
	if not (secret and signature):
		return False
	expected = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
	return hmac.compare_digest(expected, signature.strip())


def factor(config) -> float:
	return flt(config.woo_price_factor) or 1.0


def online_customer() -> str:
	if not frappe.db.exists("Customer", WALK_IN_ONLINE):
		customer = frappe.new_doc("Customer")
		customer.customer_name = WALK_IN_ONLINE
		customer.customer_type = "Individual"
		customer.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual"
		customer.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
		customer.flags.ignore_permissions = True
		customer.insert()
	return WALK_IN_ONLINE


def customer_for(order: dict) -> str:
	from iran_base.utils.sms import try_normalize_mobile

	from erpnext_iran.pos_customer import customer_for_mobile

	billing = order.get("billing") or {}
	mobile = try_normalize_mobile(billing.get("phone") or (order.get("shipping") or {}).get("phone"))
	return customer_for_mobile(mobile)["customer"] if mobile else online_customer()


def item_for(line: dict) -> str | None:
	sku = (line.get("sku") or "").strip()
	if sku and frappe.db.exists("Item", sku):
		return sku
	if line.get("product_id"):
		return frappe.db.get_value("Item", {"woo_product_id": str(line["product_id"])}, "name")
	return None


def address_text(order: dict) -> str:
	place = order.get("shipping") or {}
	if not (place.get("address_1") or place.get("city")):
		place = order.get("billing") or {}
	name = " ".join(filter(None, [place.get("first_name"), place.get("last_name")]))
	parts = [name, place.get("phone") or (order.get("billing") or {}).get("phone"), place.get("state"), place.get("city"), place.get("address_1"), place.get("address_2"), place.get("postcode")]
	return "\n".join(str(part) for part in parts if part)


def existing_order(woo_id: str) -> str | None:
	return frappe.db.get_value("Sales Order", {"woo_order_id": woo_id, "docstatus": ["<", 2]}, "name")


def refuse(woo_id: str, reason: str) -> dict:
	"""The store must get a 200 (it retries failures and then gives up on the webhook); the shop gets a to-do."""
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"description": _("WooCommerce order {0} was not entered: {1}").format(woo_id, reason),
			"priority": "High",
			"allocated_to": settings().woo_run_as or "Administrator",
		}
	).insert(ignore_permissions=True)
	return {"status": "refused", "reason": reason}


def create_sales_order(order: dict, config) -> dict:
	woo_id = str(order.get("id"))
	if name := existing_order(woo_id):
		return {"status": "duplicate", "order": name}

	if order.get("currency") and order["currency"] not in CURRENCIES:
		return refuse(woo_id, _("the store currency {0} is not rials or tomans").format(order["currency"]))
	if not (config.woo_company and config.woo_warehouse):
		return refuse(woo_id, _("Company and Online Warehouse are not set in Online Channel Settings"))

	rows, missing = [], []
	for line in order.get("line_items") or []:
		code = item_for(line)
		qty = flt(line.get("quantity"))
		if not code:
			missing.append(line.get("sku") or line.get("name") or str(line.get("product_id")))
			continue
		if qty <= 0:
			continue
		rows.append({"item_code": code, "qty": qty, "rate": flt(line.get("total")) / qty * factor(config), "warehouse": config.woo_warehouse})
	if missing:
		return refuse(woo_id, _("no item with this SKU: {0}").format(", ".join(missing)))
	if not rows:
		return refuse(woo_id, _("the order has no items"))

	doc = frappe.new_doc("Sales Order")
	doc.update(
		{
			"company": config.woo_company,
			"customer": customer_for(order),
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 3),
			"order_type": "Sales",
			"set_warehouse": config.woo_warehouse,
			"selling_price_list": config.woo_price_list or frappe.db.get_single_value("Selling Settings", "selling_price_list"),
			"sales_channel": "Website",
			"woo_order_id": woo_id,
			"po_no": str(order.get("number") or woo_id),
			"delivery_address_text": address_text(order),
		}
	)
	note = order.get("customer_note") or ""
	shipping = flt(order.get("shipping_total")) * factor(config)
	if shipping and not config.woo_shipping_account:
		note = f"{note}\n{_('Shipping')}: {shipping:,.0f}".strip()
	doc.customer_note = note
	for row in rows:
		doc.append("items", row)
	if shipping and config.woo_shipping_account:
		doc.append(
			"taxes",
			{"charge_type": "Actual", "account_head": config.woo_shipping_account, "description": _("Shipping"), "tax_amount": shipping},
		)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return {"status": "created", "order": doc.name}


def cancel_sales_order(woo_id: str) -> dict:
	name = existing_order(woo_id)
	if not name:
		return {"status": "ignored", "reason": "unknown order"}
	doc = frappe.get_doc("Sales Order", name)
	if doc.docstatus != 1 or flt(doc.per_delivered) or flt(doc.per_billed):
		doc.add_comment("Comment", _("The store cancelled this order but it is already delivered or billed. Check it by hand."))
		return {"status": "attention", "order": name}
	doc.flags.ignore_permissions = True
	doc.cancel()
	return {"status": "cancelled", "order": name}


def handle_order(order: dict, config) -> dict:
	status = (order.get("status") or "").lower()
	woo_id = str(order.get("id"))
	from frappe.utils.synchronization import filelock

	with filelock(f"woo_order_{woo_id}", timeout=30):
		if status in PAID_STATUSES:
			return create_sales_order(order, config)
		if status in CANCEL_STATUSES:
			return cancel_sales_order(woo_id)
	return {"status": "ignored", "reason": f"status {status or 'unknown'}"}


@frappe.whitelist(allow_guest=True)
def webhook():
	config = settings()
	if not cint(config.woo_enabled):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	body = frappe.request.get_data() or b""
	secret = config.get_password("woo_webhook_secret", raise_exception=False)
	if not signature_ok(body, frappe.get_request_header("X-WC-Webhook-Signature"), secret):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	try:
		order = json.loads(body)
	except ValueError:
		return {"status": "ping"}  # the store's test delivery is a form, not an order
	if not isinstance(order, dict) or "id" not in order:
		return {"status": "ping"}
	frappe.set_user(config.woo_run_as or "Administrator")
	return handle_order(order, config)


# ----------------------------------------------------------------------------- catalog


def _client(config, method: str, path: str, **kwargs):
	if not (config.woo_url and config.woo_consumer_key):
		raise WooError(_("The store address and keys are not set"))
	url = f"{config.woo_url.rstrip('/')}/wp-json/wc/v3/{path.lstrip('/')}"
	secret = config.get_password("woo_consumer_secret", raise_exception=False)
	response = requests.request(method, url, auth=(config.woo_consumer_key, secret), timeout=TIMEOUT, **kwargs)
	if response.status_code >= 400:
		raise WooError(f"{method} {path}: {response.status_code} {response.text[:200]}")
	return response.json()


def money(price: float, config) -> str:
	value = price / factor(config)
	return str(int(value)) if value == int(value) else f"{value:.2f}"


def stock_payload(item_code: str, config) -> dict:
	return {
		"regular_price": money(price_of(item_code, config.woo_price_list), config),
		"manage_stock": True,
		"stock_quantity": int(max(stock_of(item_code, config.woo_warehouse), 0)),
	}


def create_payload(item, config) -> dict:
	payload = {
		"name": item.item_name or item.name,
		"sku": item.name,
		"type": "simple",
		"status": "publish",
		"description": frappe.utils.strip_html(item.description or ""),
		**stock_payload(item.name, config),
	}
	if (item.image or "").startswith("/"):
		payload["images"] = [{"src": frappe.utils.get_url(item.image)}]
	return payload


def push_items(item_codes: list[str] | None = None) -> dict:
	"""Price and stock of the chosen items (all "Sell Online" items when none are named) to the store."""
	config = settings()
	if not cint(config.woo_enabled):
		return {"updated": 0, "created": 0, "errors": []}
	filters = {"sell_online": 1, "disabled": 0}
	if item_codes is not None:
		filters["name"] = ["in", item_codes or [""]]
	items = frappe.get_all("Item", filters, ["name", "item_name", "description", "image", "woo_product_id"])
	result = {"updated": 0, "created": 0, "errors": []}

	known = [item for item in items if item.woo_product_id]
	for start in range(0, len(known), BATCH):
		chunk = known[start : start + BATCH]
		body = {"update": [{"id": int(item.woo_product_id), **stock_payload(item.name, config)} for item in chunk]}
		try:
			_client(config, "POST", "products/batch", json=body)
			result["updated"] += len(chunk)
		except (WooError, requests.RequestException) as error:
			result["errors"].append(str(error))

	for item in (item for item in items if not item.woo_product_id):
		try:
			found = _client(config, "GET", "products", params={"sku": item.name})
			if found:
				product_id = found[0]["id"]
				_client(config, "PUT", f"products/{product_id}", json=stock_payload(item.name, config))
				result["updated"] += 1
			else:
				product_id = _client(config, "POST", "products", json=create_payload(item, config))["id"]
				result["created"] += 1
			frappe.db.set_value("Item", item.name, "woo_product_id", str(product_id), update_modified=False)
		except (WooError, requests.RequestException) as error:
			result["errors"].append(f"{item.name}: {error}")

	frappe.db.set_single_value("Online Channel Settings", "woo_last_sync", now_datetime())
	if result["errors"]:
		frappe.log_error("\n".join(result["errors"][:20]), "WooCommerce push")
	return result


def scheduled_push():
	if cint(settings().woo_enabled):
		push_items(None)


def push_after_sale(doc, method=None):
	"""A sale or its cancellation changes stock: tell the store about the online items on it, after commit."""
	if not cint(settings().woo_enabled):
		return
	codes = [row.item_code for row in doc.get("items") or []]
	online = frappe.get_all("Item", {"name": ["in", codes or [""]], "sell_online": 1, "woo_product_id": ["!=", ""]}, pluck="name")
	if online:
		frappe.enqueue("erpnext_iran.woocommerce.push_items", item_codes=online, enqueue_after_commit=True, queue="short")


@frappe.whitelist()
def sync_now() -> dict:
	frappe.only_for("System Manager")
	return push_items(None)
