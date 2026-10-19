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
	settings = frappe.get_single("System Settings")
	for fieldname, (value, stock_values) in SYSTEM_DEFAULTS.items():
		current = str(settings.get(fieldname) or "")
		if current in stock_values:
			settings.set(fieldname, value)
	settings.flags.ignore_permissions = True
	settings.save()


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
		"show_jalali_dates": 1 if get_setting("show_jalali_dates", "ERPNext Iran Settings") else 0,
	}


def persian_digits(value) -> str:
	"""For print formats: {{ doc.grand_total | persian_digits }}."""
	from iran_base.utils.numbers import to_persian_digits

	return to_persian_digits(value)
