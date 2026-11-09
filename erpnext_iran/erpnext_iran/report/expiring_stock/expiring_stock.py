"""Batches that have expired or will soon, by warehouse, with the cost of what would be lost."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from erpnext_iran.grocery import batch_stock, expiry_status, warning_days

LABELS = {"Expired": _("Expired"), "Expires Soon": _("Expires Soon"), "OK": _("OK")}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 130},
		{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
		{"fieldname": "value", "label": _("Value at Cost"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	warn = flt(filters.get("days")) if filters.get("days") not in (None, "") else warning_days()
	branches = {w: n for w, n in frappe.get_all("Store Branch", fields=["warehouse", "name"], as_list=True)}
	rows = []
	for batch in batch_stock(filters.get("company"), filters.get("warehouse"), filters.get("item_group")):
		days_left = (getdate(batch["expiry_date"]) - getdate(today())).days
		status = expiry_status(days_left, warn)
		if status == "OK" and not filters.get("show_all"):
			continue
		rows.append(
			{
				**{k: batch[k] for k in ("warehouse", "item_code", "item_name", "batch_no", "expiry_date", "qty", "uom")},
				"branch": branches.get(batch["warehouse"], ""),
				"days_left": days_left,
				"value": flt(batch["qty"]) * flt(batch["rate"]),
				"status": status,
				"status_label": LABELS[status],
			}
		)
	rows.sort(key=lambda r: (r["days_left"], r["warehouse"], r["item_code"]))
	if rows:
		lost = [r for r in rows if r["status"] != "OK"]
		rows.append({"warehouse": _("Total at risk"), "qty": sum(r["qty"] for r in lost), "value": sum(r["value"] for r in lost), "status": "", "status_label": ""})
	return rows
