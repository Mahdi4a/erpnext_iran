"""Where a sale came from, and the product feed Instagram (Meta Commerce) reads.

The catalog is a CSV of the items marked "Sell Online" with their price, availability and picture. It is
served at a secret address, so no login is needed for Meta to fetch it on a schedule."""

from __future__ import annotations

import csv
import hmac
import io

import frappe
from frappe import _
from frappe.utils import cint, flt, get_url

CATALOG_COLUMNS = ["id", "title", "description", "availability", "condition", "price", "link", "image_link", "brand"]


def settings():
	return frappe.get_single("Online Channel Settings")


def default_channel(doc, method=None):
	"""A till sale is a Store sale; anything else keeps what the person chose."""
	if doc.get("is_pos") and not doc.get("sales_channel"):
		doc.sales_channel = "Store"


def price_of(item_code: str, price_list: str | None) -> float:
	filters = {"item_code": item_code, "selling": 1}
	if price_list:
		filters["price_list"] = price_list
	rows = frappe.get_all("Item Price", filters, ["price_list_rate"], order_by="valid_from desc, modified desc", limit=1)
	return flt(rows[0].price_list_rate) if rows else 0.0


def stock_of(item_code: str, warehouse: str | None) -> float:
	filters = {"item_code": item_code}
	if warehouse:
		filters["warehouse"] = warehouse
	return sum(flt(row.actual_qty) for row in frappe.get_all("Bin", filters, ["actual_qty"]))


def catalog_rows(config=None) -> list[dict]:
	config = config or settings()
	base = (config.shop_url or get_url()).rstrip("/")
	rows = []
	items = frappe.get_all(
		"Item",
		{"sell_online": 1, "disabled": 0},
		["name", "item_name", "description", "image", "brand", "woo_product_id"],
		order_by="name",
	)
	for item in items:
		price = price_of(item.name, config.catalog_price_list)
		if price <= 0:
			continue  # Meta refuses an item with no price
		image = item.image or ""
		rows.append(
			{
				"id": item.name,
				"title": item.item_name or item.name,
				"description": frappe.utils.strip_html(item.description or "") or item.item_name or item.name,
				"availability": "in stock" if stock_of(item.name, config.catalog_warehouse) > 0 else "out of stock",
				"condition": "new",
				"price": f"{cint(price)} IRR",
				"link": f"{base}/?p={item.woo_product_id}" if item.woo_product_id else base,
				"image_link": get_url(image) if image.startswith("/") else image,
				"brand": item.brand or "",
			}
		)
	return rows


def catalog_csv(rows: list[dict]) -> str:
	out = io.StringIO()
	writer = csv.DictWriter(out, fieldnames=CATALOG_COLUMNS)
	writer.writeheader()
	writer.writerows(rows)
	return out.getvalue()


def token_ok(token: str | None) -> bool:
	secret = settings().get_password("catalog_token", raise_exception=False)
	return bool(secret and token) and hmac.compare_digest(str(token), secret)


@frappe.whitelist(allow_guest=True)
def catalog_feed(token: str | None = None):
	if not token_ok(token):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.local.response.filename = "catalog.csv"
	frappe.local.response.filecontent = catalog_csv(catalog_rows()).encode("utf-8")
	frappe.local.response.type = "download"
