from __future__ import annotations

import frappe
from frappe.utils import flt

# What follows the words, in the order Persian is read: "یک میلیون ریال", not "ریال یک میلیون"
UNITS = {"IRR": "ریال", "IRT": "تومان"}


def money_in_persian(amount, currency: str) -> str:
	"""فقط یک میلیون و دویست و پنجاه هزار ریال. Rial and Toman have no minor unit in use, so the amount is rounded."""
	from num2words import num2words

	words = num2words(round(abs(flt(amount))), lang="fa")
	return frappe._("{0} only.", context="Money in words").format(f"{words} {UNITS[currency]}")


def _company_currency(doc):
	"""Invoices carry it as an attribute only while they are validated."""
	return doc.get("company_currency") or frappe.get_cached_value(
		"Company", doc.get("company"), "default_currency"
	)


def _total(doc, prefix: str):
	"""The amount ERPNext writes in words: the rounded total, unless rounding is switched off."""
	field = f"{prefix}rounded_total"
	disabled = doc.is_rounded_total_disabled() if hasattr(doc, "is_rounded_total_disabled") else False
	if doc.meta.has_field(field) and not disabled and doc.get(field) is not None:
		return doc.get(field)
	return doc.get(f"{prefix}grand_total")


def _amounts(doc):
	"""(in_words field, amount, currency) of the document, for the fields it has."""
	if doc.doctype == "Payment Entry":
		if doc.payment_type == "Receive":
			amount, base, currency = doc.received_amount, doc.base_received_amount, doc.paid_to_account_currency
		else:
			amount, base, currency = doc.paid_amount, doc.base_paid_amount, doc.paid_from_account_currency
		yield "in_words", amount, currency
		yield "base_in_words", base, _company_currency(doc)
	elif doc.doctype == "Journal Entry":
		yield "total_amount_in_words", doc.get("total_amount"), doc.get("total_amount_currency")
	else:
		if doc.meta.has_field("in_words"):
			yield "in_words", _total(doc, ""), doc.get("currency")
		if doc.meta.has_field("base_in_words"):
			yield "base_in_words", _total(doc, "base_"), _company_currency(doc)


def set_in_words(doc, method=None):
	"""Runs after the validate of the document, which has written the words in English or in
	Frappe's order. Only Rial and Toman documents read in Persian are changed."""
	if frappe.local.lang != "fa":
		return
	if not any(doc.meta.has_field(f) for f in ("in_words", "base_in_words", "total_amount_in_words")):
		return
	for fieldname, amount, currency in _amounts(doc):
		if currency in UNITS and amount is not None:
			doc.set(fieldname, money_in_persian(amount, currency))
