"""The monthly insurance list (لیست بیمه): who, how many days, the pay insurance is taken on, and the shares.

It reads the submitted salary slips of the period. The insurable pay is the sum of the base, housing and food
rows, the same ones the default insurance formulas use; if the accountant changes those formulas, change them
here too."""

import frappe
from frappe import _
from frappe.utils import flt

INSURABLE = ("BASE", "HSG", "FOOD")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	money = {"fieldtype": "Currency", "width": 130}
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "national_id", "label": _("National ID"), "fieldtype": "Data", "width": 110},
		{"fieldname": "insurance_number", "label": _("Insurance Number"), "fieldtype": "Data", "width": 120},
		{"fieldname": "days", "label": _("Days Worked"), "fieldtype": "Float", "width": 90},
		{"fieldname": "insurable", "label": _("Insurable Pay"), **money},
		{"fieldname": "employee_share", "label": _("Employee Share"), **money},
		{"fieldname": "employer_share", "label": _("Employer Share"), **money},
		{"fieldname": "unemployment", "label": _("Unemployment"), **money},
		{"fieldname": "slip", "label": _("Salary Slip"), "fieldtype": "Link", "options": "Salary Slip", "width": 140},
	]


def get_data(filters):
	rows = frappe.db.sql(
		"""
		select
			slip.name as slip, slip.employee, slip.employee_name, slip.payment_days as days,
			emp.iran_national_id as national_id, emp.iran_insurance_number as insurance_number,
			sum(case when d.parentfield = 'earnings' and d.abbr in %(insurable)s then d.amount else 0 end) as insurable,
			sum(case when d.abbr = 'EINS' then d.amount else 0 end) as employee_share,
			sum(case when d.abbr = 'EMPINS' then d.amount else 0 end) as employer_share,
			sum(case when d.abbr = 'UNEMP' then d.amount else 0 end) as unemployment
		from `tabSalary Slip` slip
		join `tabSalary Detail` d on d.parent = slip.name
		join `tabEmployee` emp on emp.name = slip.employee
		where slip.docstatus = 1 and slip.company = %(company)s
			and slip.end_date >= %(from_date)s and slip.start_date <= %(to_date)s
		group by slip.name
		order by slip.employee
		""",
		{"company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date, "insurable": INSURABLE},
		as_dict=True,
	)
	for row in rows:
		for key in ("insurable", "employee_share", "employer_share", "unemployment", "days"):
			row[key] = flt(row[key])
	return rows
