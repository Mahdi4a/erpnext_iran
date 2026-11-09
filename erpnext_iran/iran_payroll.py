"""Iranian payroll on top of Frappe HR (HRMS): insurance, children allowance, eidi and seniority pay.

The legal figures are not in this file. The accountant enters them for each Jalali year in Iran Payroll Settings;
a payslip of a year with no row is refused, never computed with a guessed rate. Salary component formulas call
the functions below (they are added to HRMS's formula functions), for example
    iran_employee_insurance(BASE + HSG + FOOD, end_date)
"""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext_iran.jalali import current_jalali_year

REQUIRED = {
	"insurance": ("employee_insurance_pct", "employer_insurance_pct", "unemployment_pct"),
}


def year_row(on=None) -> frappe._dict:
	"""The row of Iran Payroll Settings for the Jalali year of the date, or an error that says what to fill in."""
	year = current_jalali_year(getdate(on) if on else datetime.date.today())
	settings = frappe.get_cached_doc("Iran Payroll Settings")
	for row in settings.years:
		if cint(row.jalali_year) == year:
			return frappe._dict(row.as_dict())
	frappe.throw(
		_("There are no payroll rates for the year {0}. Add a row for it in Iran Payroll Settings.").format(year),
		title=_("Iran Payroll Settings"),
	)


def insurable(amount, on=None) -> float:
	"""The part of the pay that insurance is taken on: all of it up to the ceiling of the year."""
	ceiling = flt(year_row(on).insurance_ceiling)
	amount = max(flt(amount), 0.0)
	return min(amount, ceiling) if ceiling > 0 else amount


def _share(field: str, amount, on):
	row = year_row(on)
	if row.get(field) in (None, ""):
		frappe.throw(_("{0} is empty for the year {1} in Iran Payroll Settings").format(_(field), row.jalali_year), title=_("Iran Payroll Settings"))
	return round(insurable(amount, on) * flt(row.get(field)) / 100)


def employee_insurance(amount, on=None):
	return _share("employee_insurance_pct", amount, on)


def employer_insurance(amount, on=None):
	return _share("employer_insurance_pct", amount, on)


def unemployment_insurance(amount, on=None):
	return _share("unemployment_pct", amount, on)


def child_allowance(children, on=None):
	return flt(year_row(on).child_allowance) * max(cint(children), 0)


FUNCTIONS = {
	"iran_insurable": insurable,
	"iran_employee_insurance": employee_insurance,
	"iran_employer_insurance": employer_insurance,
	"iran_unemployment": unemployment_insurance,
	"iran_child_allowance": child_allowance,
}


def install(*args, **kwargs):
	"""Adds the functions to the ones salary component formulas may call. Safe to run again."""
	try:
		from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS
	except ImportError:
		return  # HRMS is not installed on this site
	COMPONENT_EVAL_GLOBALS.update(FUNCTIONS)


# ------------------------------------------------------------------ eidi and seniority


def daily_wage(employee: str, on=None) -> float:
	"""A day's pay: the base of the employee's salary structure assignment, a thirtieth of the month."""
	base = frappe.db.get_value(
		"Salary Structure Assignment",
		{"employee": employee, "docstatus": 1, "from_date": ["<=", getdate(on)]},
		"base",
		order_by="from_date desc",
	)
	return flt(base) / 30


def eidi_amount(employee: str, jalali_year: int) -> dict:
	"""Eidi (the new year bonus) of a Jalali year: the days of wage of the year's row, capped at the days of
	minimum wage it names, in proportion to the months worked in that year."""
	from erpnext_iran.jalali import fiscal_year_dates

	start, end = fiscal_year_dates(jalali_year)
	row = year_row(end)
	if not flt(row.eidi_days):
		frappe.throw(_("Eidi (days of wage) is empty for the year {0} in Iran Payroll Settings").format(jalali_year))
	joined = getdate(frappe.db.get_value("Employee", employee, "date_of_joining") or start)
	worked_days = (end - max(start, joined)).days + 1
	share = min(worked_days / ((end - start).days + 1), 1.0)
	wage = daily_wage(employee, end)
	amount = wage * flt(row.eidi_days)
	if flt(row.eidi_cap_days) and flt(row.min_daily_wage):
		amount = min(amount, flt(row.eidi_cap_days) * flt(row.min_daily_wage))
	return {"amount": round(amount * share), "share_of_year": share, "daily_wage": wage}


def seniority_amount(employee: str, on=None) -> dict:
	"""Seniority pay (sanavat): the days per year of service of the year's row, times the years of service."""
	on = getdate(on)
	joined = frappe.db.get_value("Employee", employee, "date_of_joining")
	if not joined:
		frappe.throw(_("Employee {0} has no joining date").format(employee))
	row = year_row(on)
	if not flt(row.sanavat_days):
		frappe.throw(_("Seniority Pay (days per year of service) is empty for the year {0} in Iran Payroll Settings").format(row.jalali_year))
	years = max((on - getdate(joined)).days, 0) / 365.25
	wage = daily_wage(employee, on)
	return {"amount": round(wage * flt(row.sanavat_days) * years), "years": round(years, 2), "daily_wage": wage}


@frappe.whitelist()
def eidi(employee: str, jalali_year: int | str) -> dict:
	frappe.has_permission("Employee", "read", employee, throw=True)
	frappe.has_permission("Salary Structure Assignment", "read", throw=True)  # the answer is made from the salary
	return eidi_amount(employee, cint(jalali_year))


@frappe.whitelist()
def seniority(employee: str, on: str | None = None) -> dict:
	frappe.has_permission("Employee", "read", employee, throw=True)
	frappe.has_permission("Salary Structure Assignment", "read", throw=True)
	return seniority_amount(employee, on)


install()
