from __future__ import annotations

import frappe

CURRENCIES = {
	"IRR": {"symbol": "﷼", "fraction": ""},
	"IRT": {"symbol": "تومان", "fraction": ""},
}

# Iran value, and the values a fresh site has. A value somebody chose on purpose is left alone.
SYSTEM_DEFAULTS = {
	"number_format": ("#,###", {"", "#,###.##"}),
	"currency_precision": ("0", {"", "2", "3"}),
	"first_day_of_the_week": ("Saturday", {"", "Sunday", "Monday"}),
	"time_zone": ("Asia/Tehran", {"", "Asia/Kolkata", "Asia/Tehran"}),
}


def ensure_currency(code: str):
	"""IRR and IRT with whole numbers: Rial and Toman have no minor unit in use."""
	values = CURRENCIES[code]
	if frappe.db.exists("Currency", code):
		doc = frappe.get_doc("Currency", code)
	else:
		doc = frappe.new_doc("Currency")
		doc.currency_name = code
		doc.symbol = values["symbol"]
	doc.enabled = 1
	doc.number_format = "#,###"
	doc.smallest_currency_fraction_value = 1
	doc.fraction = values["fraction"]
	doc.flags.ignore_permissions = True
	doc.save()


def apply_system_defaults():
	"""Writes the fields one by one. A site that has not run the setup wizard has no language yet,
	and saving the whole System Settings document would fail on that."""
	for fieldname, (value, stock_values) in SYSTEM_DEFAULTS.items():
		current = str(frappe.db.get_single_value("System Settings", fieldname) or "")
		if current in stock_values:
			frappe.db.set_single_value("System Settings", fieldname, value)
	frappe.clear_cache()


def apply_defaults():
	for code in CURRENCIES:
		ensure_currency(code)
	apply_system_defaults()


def set_company_currency(doc, method=None):
	"""An Iranian company without a currency gets the Rial. IRT can be chosen on purpose."""
	if doc.get("country") == "Iran" and not doc.get("default_currency"):
		ensure_currency("IRR")
		doc.set("default_currency", "IRR")


def extend_bootinfo(bootinfo):
	from iran_base.settings import get_setting

	bootinfo.erpnext_iran = {
		"persian_digits": 1 if get_setting("use_persian_digits", "ERPNext Iran Settings") else 0,
	}


def persian_digits(value) -> str:
	"""For print formats: {{ doc.grand_total | persian_digits }}."""
	from iran_base.utils.numbers import to_persian_digits

	return to_persian_digits(value)


def iran_digits(value) -> str:
	"""For print formats: Persian digits when "Use Persian Digits" is ticked, 0-9 otherwise."""
	from iran_base.utils.numbers import to_persian_digits

	from erpnext_iran.jalali import persian_digits_enabled

	return to_persian_digits(value) if persian_digits_enabled() else str(value if value is not None else "")
