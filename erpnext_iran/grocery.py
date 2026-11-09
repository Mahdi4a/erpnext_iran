"""The food pack: expiry dates, the batch that expires first sold first, and a watch on what is about to expire.

ERPNext 16 keeps batches in Serial and Batch Bundles. Batches with an expiry date are only available once the
site has batches switched on, and the POS only picks the oldest-expiring batch when Stock Settings say so."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


def warning_days() -> int:
	from iran_base.settings import get_setting

	return cint(get_setting("expiry_warning_days", "ERPNext Iran Settings")) or 7


def apply_settings():
	"""Stock Settings for a shop that sells food. Only writes what differs, and only when asked for."""
	wanted = {"enable_serial_and_batch_no_for_item": 1, "pick_serial_and_batch_based_on": "Expiry"}
	for field, value in wanted.items():
		if frappe.db.get_single_value("Stock Settings", field) != value:
			frappe.db.set_single_value("Stock Settings", field, value)
	frappe.clear_cache(doctype="Stock Settings")


def on_settings_update(doc, method=None):
	"""ERPNext Iran Settings saved with the food pack ticked."""
	if cint(doc.get("grocery_mode")):
		apply_settings()


# ------------------------------------------------------------------ what is about to expire


def expiry_status(days_left: int, warn_days: int) -> str:
	if days_left < 0:
		return "Expired"
	return "Expires Soon" if days_left <= warn_days else "OK"


def batch_stock(company: str | None = None, warehouse: str | None = None, item_group: str | None = None) -> list[dict]:
	"""Every batch that holds stock: item, warehouse, batch, expiry date, quantity, cost rate. Quantities come from
	ERPNext's own batch function, so reserved and future-dated entries are judged the way it judges them."""
	from erpnext.stock.doctype.batch.batch import get_batch_qty

	filters = {"has_batch_no": 1, "has_expiry_date": 1, "disabled": 0}
	if item_group:
		filters["item_group"] = item_group
	items = frappe.get_all("Item", filters, ["name", "item_name", "stock_uom"])
	bins = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", [i.name for i in items] or [""]], "actual_qty": [">", 0], **({"warehouse": warehouse} if warehouse else {})},
		fields=["item_code", "warehouse", "valuation_rate"],
	)
	by_item = {i.name: i for i in items}
	rows = []
	for bin in bins:
		if company and frappe.get_cached_value("Warehouse", bin.warehouse, "company") != company:
			continue
		for batch in get_batch_qty(item_code=bin.item_code, warehouse=bin.warehouse, for_stock_levels=True) or []:
			if not batch.get("qty") or batch["qty"] <= 0 or not batch.get("expiry_date"):
				continue
			item = by_item[bin.item_code]
			rows.append(
				{
					"warehouse": bin.warehouse,
					"item_code": bin.item_code,
					"item_name": item.item_name,
					"uom": item.stock_uom,
					"batch_no": batch["batch_no"],
					"expiry_date": batch["expiry_date"],
					"qty": batch["qty"],
					"rate": bin.valuation_rate or 0,
				}
			)
	return rows


@frappe.whitelist(methods=["POST"])
def write_off_expired(company: str, warehouse: str) -> str:
	"""A draft Material Issue of every expired batch in the warehouse, for somebody to look at and submit. The
	waste leaves the stock and goes to the stock adjustment account, so it shows in the books as a loss."""
	frappe.has_permission("Stock Entry", "create", throw=True)
	if frappe.get_cached_value("Warehouse", warehouse, "company") != company:
		frappe.throw(_("Warehouse {0} does not belong to {1}").format(warehouse, company))
	from frappe.utils import getdate, today

	expired = [r for r in batch_stock(company, warehouse) if getdate(r["expiry_date"]) < getdate(today())]
	if not expired:
		frappe.throw(_("There is no expired stock in {0}").format(warehouse))
	doc = frappe.new_doc("Stock Entry")
	doc.update(
		{
			"stock_entry_type": "Material Issue",
			"company": company,
			"from_warehouse": warehouse,
			"remarks": _("Expired stock written off"),
		}
	)
	for row in expired:
		doc.append(
			"items",
			{
				"item_code": row["item_code"],
				"qty": row["qty"],
				"s_warehouse": warehouse,
				"use_serial_batch_fields": 1,
				"batch_no": row["batch_no"],
				"allow_zero_valuation_rate": 0,
			},
		)
	doc.insert()
	return doc.name


def notify_expiring():
	"""Daily: tell the stock managers what expires within the warning days, when the food pack is on."""
	from iran_base.settings import get_setting

	if not cint(get_setting("grocery_mode", "ERPNext Iran Settings")):
		return
	from frappe.utils import add_days, getdate, today

	limit = getdate(add_days(today(), warning_days()))
	soon = [r for r in batch_stock() if getdate(r["expiry_date"]) <= limit]
	if not soon:
		return
	expired = sum(1 for r in soon if getdate(r["expiry_date"]) < getdate(today()))
	subject = _("{0} batches expire within {1} days, {2} already expired").format(len(soon), warning_days(), expired)
	users = frappe.get_all("Has Role", {"role": "Stock Manager", "parenttype": "User"}, pluck="parent", distinct=True)
	for user in users:
		if user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": subject,
				"document_type": "Report",
				"document_name": "Expiring Stock",
			}
		).insert(ignore_permissions=True)
