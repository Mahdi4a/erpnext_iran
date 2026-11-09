"""Sales, cost of goods and gross profit of every branch.

A branch is a cost centre (see Store Branch). The cost of goods is what the stock ledger says left the shelf
for each invoice line, so returns come back as a negative cost and the margin stays honest.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUPS = {
	"Branch": ("", ""),
	"Branch and Day": ("si.posting_date", "posting_date"),
	"Branch and Item Group": ("item.item_group", "item_group"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group = filters.get("group_by") or "Branch"
	if group not in GROUPS:
		frappe.throw(_("Unknown grouping {0}").format(group))
	return get_columns(group), get_data(filters, group)


def get_columns(group):
	columns = [{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 200}]
	if group == "Branch and Day":
		columns.append({"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 110})
	elif group == "Branch and Item Group":
		columns.append({"fieldname": "item_group", "label": _("Item Group"), "fieldtype": "Link", "options": "Item Group", "width": 160})
	currency = {"fieldtype": "Currency", "width": 130}
	return columns + [
		{"fieldname": "invoices", "label": _("Invoices"), "fieldtype": "Int", "width": 90},
		{"fieldname": "net_sales", "label": _("Net Sales"), **currency},
		{"fieldname": "returns", "label": _("Returns"), **currency},
		{"fieldname": "cost", "label": _("Cost of Goods"), **currency},
		{"fieldname": "profit", "label": _("Gross Profit"), **currency},
		{"fieldname": "margin", "label": _("Margin %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "basket", "label": _("Average Basket"), **currency},
	]


def branch_names() -> dict:
	"""Cost centre -> the branch it belongs to. Any other cost centre keeps its own name."""
	return dict(frappe.get_all("Store Branch", fields=["cost_center", "name"], as_list=True))


def get_data(filters, group):
	extra, key = GROUPS[group]
	conditions = ["si.docstatus = 1", "si.company = %(company)s", "si.posting_date between %(from_date)s and %(to_date)s"]
	values = {"company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date}
	if filters.get("branch"):
		values["cost_center"] = frappe.db.get_value("Store Branch", filters.branch, "cost_center")
		conditions.append("item.cost_center = %(cost_center)s")

	rows = frappe.db.sql(
		f"""
		select
			item.cost_center as cost_center, {extra + ' as ' + key + ',' if extra else ''}
			count(distinct si.name) as invoices,
			sum(item.base_net_amount) as net_sales,
			sum(case when si.is_return = 1 then item.base_net_amount else 0 end) as returns,
			sum(ifnull(cost.cost, 0)) as cost
		from `tabSales Invoice Item` item
		join `tabSales Invoice` si on si.name = item.parent
		left join (
			select voucher_detail_no, -sum(stock_value_difference) as cost
			from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and is_cancelled = 0
			group by voucher_detail_no
		) cost on cost.voucher_detail_no = item.name
		where {' and '.join(conditions)}
		group by item.cost_center{', ' + extra if extra else ''}
		order by item.cost_center{', ' + extra if extra else ''}
		""",
		values,
		as_dict=True,
	)

	branches = branch_names()
	data = []
	for row in rows:
		profit = flt(row.net_sales) - flt(row.cost)
		data.append(
			{
				"branch": branches.get(row.cost_center) or row.cost_center or _("No cost centre"),
				key and key: row.get(key),
				"invoices": row.invoices,
				"net_sales": flt(row.net_sales),
				"returns": flt(row.returns),
				"cost": flt(row.cost),
				"profit": profit,
				"margin": profit / row.net_sales * 100 if flt(row.net_sales) else 0,
				"basket": flt(row.net_sales) / row.invoices if row.invoices else 0,
			}
		)
	data = [{k: v for k, v in row.items() if k} for row in data]
	if len(data) > 1:
		data.append(total_row(data))
	return data


def total_row(data):
	"""A total row that works out margin and basket from the totals, not by adding percentages."""
	net_sales = sum(row["net_sales"] for row in data)
	cost = sum(row["cost"] for row in data)
	invoices = sum(row["invoices"] for row in data)
	return {
		"branch": _("Total"),
		"invoices": invoices,
		"net_sales": net_sales,
		"returns": sum(row["returns"] for row in data),
		"cost": cost,
		"profit": net_sales - cost,
		"margin": (net_sales - cost) / net_sales * 100 if net_sales else 0,
		"basket": net_sales / invoices if invoices else 0,
	}
