"""The register an inspector asks to see: every prescription drug sold, to whom, on whose prescription, from which batch.

A return takes its drug back (negative quantity) and shows the prescription of the sale it undoes, so the book adds up."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"fieldname": "prescription_no", "label": _("Prescription Number"), "fieldtype": "Data", "width": 120},
		{"fieldname": "prescriber_name", "label": _("Prescriber"), "fieldtype": "Data", "width": 130},
		{"fieldname": "prescriber_license", "label": _("Medical Council Number"), "fieldtype": "Data", "width": 110},
		{"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data", "width": 130},
		{"fieldname": "patient_national_id", "label": _("Patient National ID"), "fieldtype": "Data", "width": 110},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 110},
		{"fieldname": "item_name", "label": _("Drug"), "fieldtype": "Data", "width": 150},
		{"fieldname": "generic_name", "label": _("Generic Name"), "fieldtype": "Data", "width": 120},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 70},
		{"fieldname": "batch_no", "label": _("Batch"), "fieldtype": "Data", "width": 110},
		{"fieldname": "controlled", "label": _("Controlled"), "fieldtype": "Check", "width": 80},
	]


def get_data(filters):
	conditions = ["si.docstatus = 1", "si.company = %(company)s", "si.posting_date between %(from_date)s and %(to_date)s"]
	values = {"company": filters.company, "from_date": filters.from_date, "to_date": filters.to_date}
	conditions.append("(it.requires_prescription = 1 or it.is_controlled_drug = 1)" if not filters.get("controlled_only") else "it.is_controlled_drug = 1")
	if filters.get("prescriber"):
		conditions.append("si.prescriber_name like %(prescriber)s")
		values["prescriber"] = f"%{filters.prescriber}%"
	return frappe.db.sql(
		f"""
		select si.posting_date, si.name as invoice,
			coalesce(nullif(si.prescription_no, ''), orig.prescription_no, '') as prescription_no,
			coalesce(nullif(si.prescriber_name, ''), orig.prescriber_name, '') as prescriber_name,
			coalesce(nullif(si.prescriber_license, ''), orig.prescriber_license, '') as prescriber_license,
			coalesce(nullif(si.patient_name, ''), orig.patient_name, '') as patient_name,
			coalesce(nullif(si.patient_national_id, ''), orig.patient_national_id, '') as patient_national_id,
			item.item_code, item.item_name, ifnull(it.generic_name, '') as generic_name, item.stock_qty as qty,
			ifnull(item.batch_no, '') as batch_no, it.is_controlled_drug as controlled
		from `tabSales Invoice Item` item
		join `tabSales Invoice` si on si.name = item.parent
		join `tabItem` it on it.name = item.item_code
		left join `tabSales Invoice` orig on orig.name = si.return_against
		where {' and '.join(conditions)}
		order by si.posting_date, si.posting_time, si.name, item.idx
		""",
		values,
		as_dict=True,
	)
