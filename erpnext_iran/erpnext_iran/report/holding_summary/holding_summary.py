"""The companies of a group side by side: what each earned in the period and what it holds at its end.

Profit and loss come from the ledger between the dates; cash, receivables, payables and stock are the balances
at the end date. Amounts stay in each company's own currency. The total row is added only when every company in
the list has the same currency: adding rials to dollars would give a number that means nothing.
"""

import frappe
from frappe import _
from frappe.utils import flt

COGS = "Cost of Goods Sold"
BALANCES = {
	"cash": ("Bank", "Cash"),
	"receivable": ("Receivable",),
	"payable": ("Payable",),
	"stock": ("Stock",),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	money = {"fieldtype": "Currency", "options": "currency", "width": 135}
	return [
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company", "width": 180},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 70},
		{"fieldname": "branches", "label": _("Branches"), "fieldtype": "Int", "width": 70},
		{"fieldname": "income", "label": _("Income"), **money},
		{"fieldname": "gross", "label": _("Gross Profit"), **money},
		{"fieldname": "net", "label": _("Net Profit"), **money},
		{"fieldname": "margin", "label": _("Net Margin %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "cash", "label": _("Cash and Bank"), **money},
		{"fieldname": "receivable", "label": _("Receivable"), **money},
		{"fieldname": "payable", "label": _("Payable"), **money},
		{"fieldname": "stock", "label": _("Stock"), **money},
	]


def companies_in_scope(company: str | None) -> list[str]:
	"""The company, and every company below it when it is a group; every company when none is given."""
	if not company:
		return frappe.get_all("Company", pluck="name", order_by="lft")
	lft, rgt = frappe.db.get_value("Company", company, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return [company]
	return frappe.get_all("Company", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name", order_by="lft")


def get_data(filters):
	companies = companies_in_scope(filters.get("company"))
	if not companies:
		return []
	params = {"companies": tuple(companies), "cogs": COGS, "from_date": filters.from_date, "to_date": filters.to_date}

	period = {
		row.company: row
		for row in frappe.db.sql(
			"""
			select gl.company,
				sum(case when a.root_type = 'Income' then gl.credit - gl.debit else 0 end) as income,
				sum(case when a.root_type = 'Expense' and a.account_type = %(cogs)s then gl.debit - gl.credit else 0 end) as cogs,
				sum(case when a.root_type = 'Expense' and ifnull(a.account_type, '') != %(cogs)s then gl.debit - gl.credit else 0 end) as expenses
			from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
			where gl.is_cancelled = 0 and gl.company in %(companies)s and a.root_type in ('Income', 'Expense')
				and gl.posting_date between %(from_date)s and %(to_date)s
				and ifnull(gl.voucher_type, '') != 'Period Closing Voucher'
			group by gl.company
			""",
			params,
			as_dict=True,
		)
	}
	balance = {
		row.company: row
		for row in frappe.db.sql(
			"""
			select gl.company,
				sum(case when a.account_type in ('Bank', 'Cash') then gl.debit - gl.credit else 0 end) as cash,
				sum(case when a.account_type = 'Receivable' then gl.debit - gl.credit else 0 end) as receivable,
				sum(case when a.account_type = 'Payable' then gl.credit - gl.debit else 0 end) as payable,
				sum(case when a.account_type = 'Stock' then gl.debit - gl.credit else 0 end) as stock
			from `tabGL Entry` gl join `tabAccount` a on a.name = gl.account
			where gl.is_cancelled = 0 and gl.company in %(companies)s and gl.posting_date <= %(to_date)s
			group by gl.company
			""",
			params,
			as_dict=True,
		)
	}
	branches = dict(
		frappe.db.sql(
			"select company, count(*) from `tabStore Branch` where disabled = 0 and company in %(companies)s group by company",
			params,
		)
	)

	data = []
	for company in companies:
		p, b = period.get(company) or {}, balance.get(company) or {}
		income, cogs, expenses = flt(p.get("income")), flt(p.get("cogs")), flt(p.get("expenses"))
		net = income - cogs - expenses
		data.append(
			{
				"company": company,
				"currency": frappe.get_cached_value("Company", company, "default_currency"),
				"branches": branches.get(company, 0),
				"income": income,
				"gross": income - cogs,
				"net": net,
				"margin": net / income * 100 if income else 0,
				"cash": flt(b.get("cash")),
				"receivable": flt(b.get("receivable")),
				"payable": flt(b.get("payable")),
				"stock": flt(b.get("stock")),
			}
		)
	if len(data) > 1 and len({row["currency"] for row in data}) == 1:
		data.append(total_row(data))
	return data


def total_row(data):
	income = sum(r["income"] for r in data)
	net = sum(r["net"] for r in data)
	return {
		"company": _("Total"),
		"currency": data[0]["currency"],
		"branches": sum(r["branches"] for r in data),
		"income": income,
		"gross": sum(r["gross"] for r in data),
		"net": net,
		"margin": net / income * 100 if income else 0,
		**{key: sum(r[key] for r in data) for key in ("cash", "receivable", "payable", "stock")},
	}
