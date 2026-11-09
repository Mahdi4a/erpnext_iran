from __future__ import annotations

import datetime

import frappe
from frappe.utils import getdate
from iran_base.utils.jalali import to_jalali

# Parts of a naming series: ACC-SINV-.JY.-.#####  gives ACC-SINV-1405-00001
VARIABLES = {
	"JY": "Jalali year, 4 digits",
	"JYY": "Jalali year, 2 digits",
	"JM": "Jalali month, 2 digits",
	"JD": "Jalali day, 2 digits",
}


def document_date(doc) -> datetime.date:
	"""The date the document is for: its posting or transaction date, else today. The same rule ERPNext uses for FY."""
	value = None
	if doc is not None:
		value = doc.get("posting_date") or doc.get("transaction_date") or doc.get("date")
	return getdate(value) if value else getdate()


def parse_variable(doc, variable: str) -> str:
	year, month, day = to_jalali(document_date(doc))
	return {
		"JY": f"{year:04d}",
		"JYY": f"{year % 100:02d}",
		"JM": f"{month:02d}",
		"JD": f"{day:02d}",
	}[variable]


# The documents whose number carries a year
SERIES_DOCTYPES = (
	"Sales Invoice",
	"Purchase Invoice",
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Purchase Order",
	"Purchase Receipt",
	"Payment Entry",
	"Journal Entry",
)


def _set_series_property(doctype: str, prop: str, value: str):
	"""A Property Setter of the naming_series field, changed if it is already there."""
	name = frappe.db.get_value(
		"Property Setter", {"doc_type": doctype, "field_name": "naming_series", "property": prop}
	)
	if name:
		frappe.db.set_value("Property Setter", name, "value", value)
	else:
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"fieldname": "naming_series",
				"property": prop,
				"value": value,
				"property_type": "Text",
			}
		)
	frappe.clear_cache(doctype=doctype)


def _series_options(doctype: str) -> list[str]:
	return [o for o in (frappe.get_meta(doctype).get_field("naming_series").options or "").split("\n") if o]


@frappe.whitelist(methods=["POST"])
def add_jalali_series() -> list[str]:
	"""For every document above, adds a series with the Jalali year next to each one that has the
	Gregorian year (ACC-SINV-.YYYY.-.#####, ACC-SINV-.JY.-.#####) and makes the first of them the
	default. Existing series and documents are not touched; the new series counts from 1."""
	frappe.only_for("System Manager")
	changed = []
	for doctype in SERIES_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		options = _series_options(doctype)
		jalali = [o.replace(".YYYY.", ".JY.") for o in options if ".YYYY." in o]
		added = [o for o in jalali if o not in options]
		if not added:
			continue
		_set_series_property(doctype, "options", "\n".join(added + options))
		_set_series_property(doctype, "default", added[0])
		changed.append(doctype)
	return changed


@frappe.whitelist(methods=["POST"])
def remove_jalali_series() -> list[str]:
	"""Takes the Jalali series away again. Documents already numbered with them keep their names."""
	frappe.only_for("System Manager")
	changed = []
	for doctype in SERIES_DOCTYPES:
		options = _series_options(doctype)
		kept = [o for o in options if ".JY." not in o]
		if kept == options or not kept:
			continue
		_set_series_property(doctype, "options", "\n".join(kept))
		_set_series_property(doctype, "default", kept[0])
		changed.append(doctype)
	return changed
