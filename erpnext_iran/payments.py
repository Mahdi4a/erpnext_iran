from __future__ import annotations

import frappe

# Mode of Payment name -> type. The stock modes (Cash, Cheque, Wire Transfer...) stay as they are.
PAYMENT_MODES = {
	"کارت‌به‌کارت": "Bank",
	"کارت‌خوان": "Bank",
	"درگاه پرداخت اینترنتی": "Bank",
	"پایا و ساتنا": "Bank",
}

# 1 Toman is 10 Rial by definition, so this rate is not a market rate and never changes
FIXED_RATES = [("IRT", "IRR", 10), ("IRR", "IRT", 0.1)]
FIXED_RATE_DATE = "2000-01-01"


def ensure_payment_modes():
	for name, mode_type in PAYMENT_MODES.items():
		if frappe.db.exists("Mode of Payment", name):
			continue
		mode = frappe.new_doc("Mode of Payment")
		mode.mode_of_payment = name
		mode.type = mode_type
		mode.flags.ignore_permissions = True
		mode.insert()


def ensure_fixed_rates():
	"""Rial and Toman documents can be mixed. The Dollar and other rates are market rates and are
	entered by hand in Currency Exchange."""
	for from_currency, to_currency, rate in FIXED_RATES:
		if not (frappe.db.exists("Currency", from_currency) and frappe.db.exists("Currency", to_currency)):
			continue
		if frappe.db.exists(
			"Currency Exchange", {"from_currency": from_currency, "to_currency": to_currency}
		):
			continue
		doc = frappe.new_doc("Currency Exchange")
		doc.date = FIXED_RATE_DATE
		doc.from_currency = from_currency
		doc.to_currency = to_currency
		doc.exchange_rate = rate
		doc.for_buying = 1
		doc.for_selling = 1
		doc.flags.ignore_permissions = True
		doc.insert()


def save_dollar_rate(rial_per_dollar: float):
	"""The Dollar rate of today as Currency Exchange, to the Rial and to the Toman. A rate that is already
	there for today is changed, so entering it again in the same day corrects it."""
	today = frappe.utils.today()
	for to_currency, rate in (("IRR", rial_per_dollar), ("IRT", rial_per_dollar / 10)):
		if not frappe.db.exists("Currency", to_currency):
			continue
		name = frappe.db.get_value(
			"Currency Exchange", {"date": today, "from_currency": "USD", "to_currency": to_currency}
		)
		doc = frappe.get_doc("Currency Exchange", name) if name else frappe.new_doc("Currency Exchange")
		doc.update(
			{
				"date": today,
				"from_currency": "USD",
				"to_currency": to_currency,
				"exchange_rate": rate,
				"for_buying": 1,
				"for_selling": 1,
			}
		)
		doc.flags.ignore_permissions = True
		doc.save()
