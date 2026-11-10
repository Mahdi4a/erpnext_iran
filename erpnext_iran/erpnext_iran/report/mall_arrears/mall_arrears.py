"""What tenants owe: the unpaid mall invoices, with how late each is."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today

BUCKETS = ((0, "Not Due"), (30, "1-30"), (60, "31-60"), (90, "61-90"))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "tenant", "label": _("Tenant"), "fieldtype": "Link", "options": "Customer", "width": 150},
		{"fieldname": "unit", "label": _("Unit"), "fieldtype": "Link", "options": "Mall Unit", "width": 90},
		{"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 90},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "outstanding", "label": _("Outstanding"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "days_late", "label": _("Days Late"), "fieldtype": "Int", "width": 80},
		{"fieldname": "bucket", "label": _("Age"), "fieldtype": "Data", "width": 80},
	]


def bucket(days_late: int) -> str:
	"""Not due, or how many days late in steps of thirty."""
	if days_late <= 0:
		return "Not Due"
	if days_late <= 30:
		return "1-30"
	if days_late <= 60:
		return "31-60"
	if days_late <= 90:
		return "61-90"
	return "90+"


def get_data(filters):
	as_on = getdate(filters.get("as_on") or today())
	conditions, values = ["si.docstatus = 1", "si.company = %(company)s", "si.outstanding_amount > 0", "ifnull(si.mall_lease, '') != ''", "si.posting_date <= %(as_on)s"], {"company": filters.company, "as_on": as_on}
	if filters.get("tenant"):
		conditions.append("si.customer = %(tenant)s")
		values["tenant"] = filters.tenant
	rows = frappe.db.sql(
		f"""select si.customer as tenant, lease.unit, si.name as invoice, si.mall_period as period, si.due_date, si.outstanding_amount as outstanding
		from `tabSales Invoice` si left join `tabMall Lease` lease on lease.name = si.mall_lease
		where {' and '.join(conditions)} order by si.customer, si.due_date""",
		values,
		as_dict=True,
	)
	data = []
	for row in rows:
		late = date_diff(as_on, row.due_date) if row.due_date else 0
		data.append({**row, "outstanding": flt(row.outstanding), "days_late": max(late, 0), "bucket": bucket(late)})
	if data:
		data.append({"tenant": _("Total"), "outstanding": sum(r["outstanding"] for r in data)})
	return data
