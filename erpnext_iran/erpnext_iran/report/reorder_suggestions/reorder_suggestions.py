"""What each branch should order, from how fast it sells.

For every item and warehouse: the average sold per day over the last N days, the days the stock will last at that
speed, and how much to order so that, after the delivery time, a reserve of days is still on the shelf.

    to order = average per day x (delivery days + reserve days) - stock

Only sales invoices that move stock are counted, returns take away. Nothing is ordered for an item that sold
nothing in the period: a dead item needs a decision, not a purchase.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today
from frappe.utils import ceil as ceil_value


def execute(filters=None):
	filters = frappe._dict(filters or {})
	for name in ("sales_days", "lead_days", "safety_days"):
		if flt(filters.get(name)) < 0 or (name == "sales_days" and flt(filters.get(name)) <= 0):
			frappe.throw(_("{0} must be a positive number of days").format(name))
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 130},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "stock", "label": _("In Stock"), "fieldtype": "Float", "width": 90},
		{"fieldname": "sold", "label": _("Sold"), "fieldtype": "Float", "width": 90},
		{"fieldname": "per_day", "label": _("Per Day"), "fieldtype": "Float", "precision": 2, "width": 80},
		{"fieldname": "cover_days", "label": _("Days of Stock"), "fieldtype": "Float", "precision": 1, "width": 100},
		{"fieldname": "to_order", "label": _("To Order"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 70},
	]


def suggest(stock: float, sold: float, sales_days: float, lead_days: float, safety_days: float) -> dict | None:
	"""Per-day speed, days of cover and the quantity to order (whole units, rounded up); None when nothing sold."""
	if sold <= 0:
		return None
	per_day = sold / sales_days
	need = per_day * (lead_days + safety_days) - max(stock, 0)
	return {"per_day": per_day, "cover_days": max(stock, 0) / per_day, "to_order": float(ceil_value(need)) if need > 0 else 0.0}


def get_data(filters):
	sales_days = flt(filters.sales_days)
	since = add_days(getdate(today()), -int(sales_days))
	conditions, values = [], {"company": filters.company, "since": since}
	if filters.get("warehouse"):
		conditions.append("item.warehouse = %(warehouse)s")
		values["warehouse"] = filters.warehouse
	if filters.get("item_group"):
		conditions.append("it.item_group = %(item_group)s")
		values["item_group"] = filters.item_group
	extra = (" and " + " and ".join(conditions)) if conditions else ""
	sold = frappe.db.sql(
		f"""
		select item.warehouse, item.item_code, sum(item.stock_qty) as sold, max(it.item_name) as item_name, max(it.stock_uom) as uom
		from `tabSales Invoice Item` item
		join `tabSales Invoice` si on si.name = item.parent
		join `tabItem` it on it.name = item.item_code
		where si.docstatus = 1 and si.update_stock = 1 and si.company = %(company)s and si.posting_date >= %(since)s
			and it.is_stock_item = 1 and ifnull(item.warehouse, '') != '' {extra}
		group by item.warehouse, item.item_code
		""",
		values,
		as_dict=True,
	)
	if not sold:
		return []
	bins = {
		(row.warehouse, row.item_code): flt(row.actual_qty)
		for row in frappe.get_all(
			"Bin", {"item_code": ["in", list({r.item_code for r in sold})], "warehouse": ["in", list({r.warehouse for r in sold})]}, ["warehouse", "item_code", "actual_qty"]
		)
	}
	branches = dict(frappe.get_all("Store Branch", fields=["warehouse", "name"], as_list=True))
	rows = []
	for row in sold:
		stock = bins.get((row.warehouse, row.item_code), 0.0)
		result = suggest(stock, flt(row.sold), sales_days, flt(filters.lead_days), flt(filters.safety_days))
		if result is None or (filters.get("only_needed") and not result["to_order"]):
			continue
		rows.append(
			{
				"warehouse": row.warehouse,
				"branch": branches.get(row.warehouse, ""),
				"item_code": row.item_code,
				"item_name": row.item_name,
				"stock": stock,
				"sold": flt(row.sold),
				"uom": row.uom,
				**result,
			}
		)
	rows.sort(key=lambda r: (r["cover_days"], r["warehouse"], r["item_code"]))
	return rows


@frappe.whitelist(methods=["POST"])
def make_material_request(company: str, rows, delivery_days: int = 3) -> str:
	"""A draft purchase Material Request for the rows of the report that have something to order."""
	frappe.has_permission("Material Request", "create", throw=True)
	rows = frappe.parse_json(rows)
	if not isinstance(rows, list):
		frappe.throw(_("No rows to order"))
	doc = frappe.new_doc("Material Request")
	doc.update({"material_request_type": "Purchase", "company": company, "schedule_date": add_days(today(), int(delivery_days))})
	for row in rows:
		qty = flt(row.get("to_order"))
		if qty <= 0 or not row.get("item_code") or not row.get("warehouse"):
			continue
		if frappe.get_cached_value("Warehouse", row["warehouse"], "company") != company:
			frappe.throw(_("Warehouse {0} does not belong to {1}").format(row["warehouse"], company))
		doc.append("items", {"item_code": row["item_code"], "qty": qty, "warehouse": row["warehouse"], "schedule_date": doc.schedule_date})
	if not doc.items:
		frappe.throw(_("There is nothing to order"))
	doc.insert()
	return doc.name
