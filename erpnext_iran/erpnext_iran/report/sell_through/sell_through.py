"""How much of each style has been sold: sold / (sold + still in stock).

It is the number a buyer lives by. A style at 80% after a month is a reorder; at 10% after a season it is a
clearance. Sold counts what left on sales invoices in the period (returns take away); stock is what is on the
shelves now, in the warehouses of the company."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	money = {"fieldtype": "Currency", "width": 130}
	return [
		{"fieldname": "style", "label": _("Style"), "fieldtype": "Link", "options": "Item", "width": 120},
		{"fieldname": "style_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "season", "label": _("Season"), "fieldtype": "Data", "width": 80},
		{"fieldname": "sold", "label": _("Sold"), "fieldtype": "Float", "width": 80},
		{"fieldname": "stock", "label": _("In Stock"), "fieldtype": "Float", "width": 80},
		{"fieldname": "sell_through", "label": _("Sell Through %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "revenue", "label": _("Revenue"), **money},
		{"fieldname": "stock_value", "label": _("Stock at Cost"), **money},
	]


def percent(sold: float, stock: float) -> float:
	"""Share sold of what the shop had: 0 when it had nothing to sell."""
	total = max(sold, 0) + max(stock, 0)
	return max(sold, 0) / total * 100 if total else 0.0


def get_data(filters):
	warehouses = tuple(frappe.get_all("Warehouse", {"company": filters.company, "is_group": 0}, pluck="name")) or ("",)
	season = "and template.season = %(season)s" if filters.get("season") else ""
	values = {"company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date, "season": filters.get("season"), "warehouses": warehouses}
	sold = {
		r.style: r
		for r in frappe.db.sql(
			f"""
			select variant.variant_of as style, sum(item.stock_qty) as sold, sum(item.base_net_amount) as revenue
			from `tabSales Invoice Item` item
			join `tabSales Invoice` si on si.name = item.parent
			join `tabItem` variant on variant.name = item.item_code and variant.variant_of is not null
			join `tabItem` template on template.name = variant.variant_of
			where si.docstatus = 1 and si.update_stock = 1 and si.company = %(company)s
				and si.posting_date between %(from_date)s and %(to_date)s {season}
			group by variant.variant_of
			""",
			values,
			as_dict=True,
		)
	}
	stock = {
		r.style: r
		for r in frappe.db.sql(
			f"""
			select variant.variant_of as style, sum(bin.actual_qty) as stock, sum(bin.stock_value) as stock_value
			from `tabBin` bin
			join `tabItem` variant on variant.name = bin.item_code and variant.variant_of is not null
			join `tabItem` template on template.name = variant.variant_of
			where bin.warehouse in %(warehouses)s {season}
			group by variant.variant_of
			""",
			values,
			as_dict=True,
		)
	}
	names = {r.name: r for r in frappe.get_all("Item", {"name": ["in", list(set(sold) | set(stock)) or [""]]}, ["name", "item_name", "season"])}
	data = []
	for style in sorted(set(sold) | set(stock)):
		s, st = sold.get(style), stock.get(style)
		sold_qty, stock_qty = flt(s.sold if s else 0), flt(st.stock if st else 0)
		data.append(
			{
				"style": style,
				"style_name": names[style].item_name,
				"season": names[style].season or "",
				"sold": sold_qty,
				"stock": stock_qty,
				"sell_through": percent(sold_qty, stock_qty),
				"revenue": flt(s.revenue if s else 0),
				"stock_value": flt(st.stock_value if st else 0),
			}
		)
	data.sort(key=lambda r: (-r["sell_through"], r["style"]))
	return data
