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
