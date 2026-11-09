"""Net profit of every branch, from the ledger.

Branch Profit looks at invoices: sales less the cost of the goods. This one looks at the books, so the rent,
wages and advertising booked to a branch (or shared out to it by a Cost Center Allocation) come off as well.
What no cost centre carries is shown as its own line, "Not charged to a branch": the head office's share.
"""

import frappe
from frappe import _
from frappe.utils import flt

COGS = "Cost of Goods Sold"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group = filters.get("group_by") or "Branch"
	if group not in ("Branch", "Branch and Month"):
		frappe.throw(_("Unknown grouping {0}").format(group))
	return get_columns(group), get_data(filters, group)


def get_columns(group):
	columns = [{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Data", "width": 200}]
	if group == "Branch and Month":
		columns.append({"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 90})
	money = {"fieldtype": "Currency", "width": 140}
	return columns + [
		{"fieldname": "income", "label": _("Income"), **money},
		{"fieldname": "cogs", "label": _("Cost of Goods"), **money},
		{"fieldname": "gross", "label": _("Gross Profit"), **money},
		{"fieldname": "expenses", "label": _("Operating Expenses"), **money},
		{"fieldname": "net", "label": _("Net Profit"), **money},
		{"fieldname": "margin", "label": _("Net Margin %"), "fieldtype": "Percent", "width": 100},
	]


def branch_names() -> dict:
	return dict(frappe.get_all("Store Branch", fields=["cost_center", "name"], as_list=True))


def get_data(filters, group):
	month = "date_format(gl.posting_date, '%%Y-%%m')" if group == "Branch and Month" else "''"
	rows = frappe.db.sql(
		f"""
		select ifnull(gl.cost_center, '') as cost_center, {month} as month,
			sum(case when a.root_type = 'Income' then gl.credit - gl.debit else 0 end) as income,
			sum(case when a.root_type = 'Expense' and a.account_type = %(cogs)s then gl.debit - gl.credit else 0 end) as cogs,
			sum(case when a.root_type = 'Expense' and ifnull(a.account_type, '') != %(cogs)s then gl.debit - gl.credit else 0 end) as expenses
		from `tabGL Entry` gl
		join `tabAccount` a on a.name = gl.account
		where gl.is_cancelled = 0 and gl.company = %(company)s
			and gl.posting_date between %(from_date)s and %(to_date)s
			and a.root_type in ('Income', 'Expense')
			and ifnull(gl.voucher_type, '') != 'Period Closing Voucher'
		group by ifnull(gl.cost_center, ''), {month}
		order by 1, 2
		""",
		{"cogs": COGS, "company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date},
		as_dict=True,
	)
	branches = branch_names()
	data = []
	for row in rows:
		gross = flt(row.income) - flt(row.cogs)
		net = gross - flt(row.expenses)
		data.append(
			{
				"branch": branches.get(row.cost_center) or row.cost_center or _("Not charged to a branch"),
				"month": row.month,
				"income": flt(row.income),
				"cogs": flt(row.cogs),
				"gross": gross,
				"expenses": flt(row.expenses),
				"net": net,
				"margin": net / flt(row.income) * 100 if flt(row.income) else 0,
			}
		)
	if len(data) > 1:
		data.append(total_row(data))
	return [{k: v for k, v in row.items() if k != "month" or group == "Branch and Month"} for row in data]


def total_row(data):
	income = sum(r["income"] for r in data)
	cogs = sum(r["cogs"] for r in data)
	expenses = sum(r["expenses"] for r in data)
	net = income - cogs - expenses
	return {
		"branch": _("Total"),
		"month": "",
		"income": income,
		"cogs": cogs,
		"gross": income - cogs,
		"expenses": expenses,
		"net": net,
		"margin": net / income * 100 if income else 0,
	}
