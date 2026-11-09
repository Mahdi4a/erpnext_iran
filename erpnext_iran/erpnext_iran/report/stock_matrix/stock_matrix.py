"""The shelf of a clothing shop on one page: a row for every style in a colour, a column for every size.

An empty cell is a size the shop has run out of, which is what the buyer looks for first."""

import frappe
from frappe import _
from frappe.utils import flt

SIZE, COLOUR = "Size", "Colour"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	sizes, rows = get_matrix(filters)
	return get_columns(sizes), rows


def get_columns(sizes):
	columns = [
		{"fieldname": "style", "label": _("Style"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "style_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "season", "label": _("Season"), "fieldtype": "Data", "width": 80},
		{"fieldname": "colour", "label": _("Colour"), "fieldtype": "Data", "width": 100},
	]
	columns += [{"fieldname": f"size_{i}", "label": size, "fieldtype": "Float", "width": 60} for i, size in enumerate(sizes)]
	columns.append({"fieldname": "total", "label": _("Total"), "fieldtype": "Float", "width": 80})
	return columns


def size_order() -> dict:
	"""Sizes in the order the attribute lists them (S, M, L, XL), not alphabetically."""
	rows = frappe.get_all("Item Attribute Value", {"parent": SIZE, "parenttype": "Item Attribute"}, ["attribute_value"], order_by="idx")
	return {r.attribute_value: i for i, r in enumerate(rows)}


def get_matrix(filters):
	conditions, values = ["variant.disabled = 0", "variant.variant_of is not null"], {}
	if filters.get("style"):
		conditions.append("variant.variant_of = %(style)s")
		values["style"] = filters.style
	if filters.get("season"):
		conditions.append("template.season = %(season)s")
		values["season"] = filters.season
	warehouses = (
		[filters.warehouse]
		if filters.get("warehouse")
		else frappe.get_all("Warehouse", {"company": filters.company, "is_group": 0}, pluck="name")
	)
	if not warehouses:
		return [], []
	values["warehouses"] = tuple(warehouses)
	rows = frappe.db.sql(
		f"""
		select variant.variant_of as style, template.item_name as style_name, ifnull(template.season, '') as season,
			size_attr.attribute_value as size, colour_attr.attribute_value as colour,
			ifnull(sum(bin.actual_qty), 0) as qty
		from `tabItem` variant
		join `tabItem` template on template.name = variant.variant_of
		join `tabItem Variant Attribute` size_attr on size_attr.parent = variant.name and size_attr.attribute = '{SIZE}'
		join `tabItem Variant Attribute` colour_attr on colour_attr.parent = variant.name and colour_attr.attribute = '{COLOUR}'
		left join `tabBin` bin on bin.item_code = variant.name and bin.warehouse in %(warehouses)s
		where {' and '.join(conditions)}
		group by variant.variant_of, colour_attr.attribute_value, size_attr.attribute_value
		""",
		values,
		as_dict=True,
	)
	order = size_order()
	sizes = sorted({r["size"] for r in rows}, key=lambda s: (order.get(s, len(order)), s))
	index = {size: i for i, size in enumerate(sizes)}
	grouped: dict[tuple, dict] = {}
	for row in rows:
		key = (row["style"], row["colour"])
		line = grouped.setdefault(key, {"style": row["style"], "style_name": row["style_name"], "season": row["season"], "colour": row["colour"], "total": 0.0})
		line[f"size_{index[row['size']]}"] = flt(row["qty"])
		line["total"] += flt(row["qty"])
	data = sorted(grouped.values(), key=lambda r: (r["style"], r["colour"]))
	if filters.get("only_in_stock"):
		data = [r for r in data if r["total"] > 0]
	return sizes, data
