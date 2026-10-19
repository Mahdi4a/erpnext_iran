from __future__ import annotations

import datetime

import frappe
from frappe import _
from iran_base.utils.jalali import format_jalali, is_jalali_leap, jalali_to_gregorian, to_jalali


def fiscal_year_dates(jalali_year: int) -> tuple[datetime.date, datetime.date]:
	"""1 Farvardin to the last day of Esfand (29 or 30) of the Jalali year, as Gregorian dates."""
	start = datetime.date(*jalali_to_gregorian(jalali_year, 1, 1))
	end = datetime.date(*jalali_to_gregorian(jalali_year + 1, 1, 1)) - datetime.timedelta(days=1)
	return start, end


def needs_no_exception(start: datetime.date, end: datetime.date) -> bool:
	"""ERPNext wants the end date to be exactly one Gregorian year after the start. A Jalali year is
	one day shorter or longer in some years (the leap days of the two calendars differ), and ERPNext
	only lets such a year through when "Is Short Year" is ticked, so that is what is done then."""
	expected = start.replace(year=start.year + 1) - datetime.timedelta(days=1)
	return end == expected


def current_jalali_year(today: datetime.date | None = None) -> int:
	return to_jalali(today or datetime.date.today())[0]


@frappe.whitelist()
def create_fiscal_year(jalali_year: int | str, company: str | None = None) -> str:
	"""A Fiscal Year named after the Jalali year, e.g. 1404. Does nothing if it already exists.

	ERPNext refuses a year that overlaps another one unless both are limited to companies, so pass
	a company when the site already has Gregorian years.
	"""
	frappe.only_for(("Accounts Manager", "System Manager"))
	return ensure_fiscal_year(int(jalali_year), company)


def ensure_fiscal_year(jalali_year: int, company: str | None = None) -> str:
	name = str(jalali_year)
	if frappe.db.exists("Fiscal Year", name):
		return name

	start, end = fiscal_year_dates(jalali_year)
	doc = {
		"doctype": "Fiscal Year",
		"year": name,
		"year_start_date": start,
		"year_end_date": end,
		"is_short_year": 0 if needs_no_exception(start, end) else 1,
	}
	if company:
		doc["companies"] = [{"company": company}]
	frappe.get_doc(doc).insert(ignore_permissions=True)
	return name


def ensure_current_and_next_fiscal_years():
	"""Run daily, so the books never reach a date without a Fiscal Year."""
	year = current_jalali_year()
	for jalali_year in (year, year + 1):
		try:
			ensure_fiscal_year(jalali_year)
		except Exception:
			# E.g. it overlaps a year somebody made by hand. That must not stop a migrate or the
			# scheduler, and the choice (limit one of them to a company) is theirs.
			frappe.log_error(title=_("Could not create the Jalali fiscal year {0}").format(jalali_year))


def persian_digits_enabled() -> bool:
	from iran_base.settings import get_setting

	return bool(get_setting("use_persian_digits", "ERPNext Iran Settings"))


def jalali_date(value, with_month_name: bool = False) -> str:
	"""For print formats: {{ doc.posting_date | jalali_date }} or {{ doc.posting_date | jalali_date(True) }}."""
	if not value:
		return ""
	return format_jalali(value, persian_digits=persian_digits_enabled(), with_month_name=with_month_name)
