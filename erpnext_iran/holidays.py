from __future__ import annotations

import datetime

import frappe
from iran_base.utils.jalali import jalali_to_gregorian

from erpnext_iran.jalali import current_jalali_year, fiscal_year_dates

# Holidays of the Jalali calendar. They fall on the same Jalali date every year.
SOLAR_HOLIDAYS = [
	(1, 1, "جشن نوروز"),
	(1, 2, "جشن نوروز"),
	(1, 3, "جشن نوروز"),
	(1, 4, "جشن نوروز"),
	(1, 12, "روز جمهوری اسلامی"),
	(1, 13, "روز طبیعت"),
	(3, 14, "رحلت امام خمینی"),
	(3, 15, "قیام ۱۵ خرداد"),
	(11, 22, "پیروزی انقلاب اسلامی"),
	(12, 29, "روز ملی شدن صنعت نفت ایران"),
]

# Religious holidays follow the lunar calendar and the sighting of the moon, so the Jalali date
# is different every year and is only known when the official calendar is published. A year
# without an entry here gets no holiday list until its dates are added.
# 1405: the calendars of asriran.com and nabzebourse.com agree on these. nabzebourse.com also
# lists 25 Farvardin (martyrdom of Imam Jafar al-Sadiq), asriran.com does not, so it is left out.
# Check them against the calendar of the Supreme Council of Cultural Revolution.
LUNAR_HOLIDAYS = {
	1405: [
		(1, 1, "عید سعید فطر"),
		(1, 2, "تعطیلی به مناسبت عید سعید فطر"),
		(3, 6, "عید سعید قربان"),
		(3, 14, "عید سعید غدیر خم"),
		(4, 3, "تاسوعای حسینی"),
		(4, 4, "عاشورای حسینی"),
		(5, 13, "اربعین حسینی"),
		(5, 21, "رحلت پیامبر اکرم و شهادت امام حسن مجتبی"),
		(5, 22, "شهادت امام رضا"),
		(6, 8, "ولادت پیامبر اکرم و امام جعفر صادق"),
		(10, 2, "ولادت امام علی و روز پدر"),
		(10, 16, "مبعث پیامبر اکرم"),
		(11, 4, "ولادت حضرت مهدی و نیمه شعبان"),
		(12, 9, "شهادت امام علی"),
		(12, 19, "عید سعید فطر"),
		(12, 20, "تعطیلی به مناسبت عید سعید فطر"),
	],
}

WEEKLY_OFF = "Friday"


def holiday_list_name(jalali_year: int) -> str:
	return f"تعطیلات رسمی ایران {jalali_year}"


def official_holidays(jalali_year: int) -> list[tuple[datetime.date, str]]:
	"""(Gregorian date, occasion) of the holidays of the year that are not on a Friday, in order.
	An occasion on both calendars is written once with both names."""
	occasions: dict[datetime.date, list[str]] = {}
	for month, day, description in SOLAR_HOLIDAYS + LUNAR_HOLIDAYS[jalali_year]:
		date = datetime.date(*jalali_to_gregorian(jalali_year, month, day))
		if date.strftime("%A") == WEEKLY_OFF:
			continue
		names = occasions.setdefault(date, [])
		if description not in names and not (description == "جشن نوروز" and "جشن نوروز" in names):
			names.append(description)
	return [(date, " و ".join(names)) for date, names in sorted(occasions.items())]


def ensure_holiday_list(jalali_year: int) -> str | None:
	"""A Holiday List with every Friday and the official holidays of the Jalali year. Nothing is done
	when the list exists, so a list somebody edited is kept, or when the year has no lunar dates yet."""
	if jalali_year not in LUNAR_HOLIDAYS:
		return None
	name = holiday_list_name(jalali_year)
	if frappe.db.exists("Holiday List", name):
		return name

	start, end = fiscal_year_dates(jalali_year)
	doc = frappe.new_doc("Holiday List")
	doc.holiday_list_name = name
	doc.from_date = start
	doc.to_date = end
	doc.weekly_off = WEEKLY_OFF
	doc.get_weekly_off_dates()
	for date, description in official_holidays(jalali_year):
		doc.append("holidays", {"holiday_date": date, "description": description, "weekly_off": 0})
	doc.flags.ignore_permissions = True
	doc.insert()
	return name


def ensure_holiday_lists():
	"""The current and the next Jalali year, when their dates are known."""
	year = current_jalali_year()
	names = [ensure_holiday_list(y) for y in (year, year + 1)]
	set_company_holiday_list(next((n for n in names if n), None))


def set_company_holiday_list(name: str | None):
	"""An Iranian company with no holiday list gets the first one."""
	if not name:
		return
	for company in frappe.get_all("Company", filters={"country": "Iran", "default_holiday_list": ["is", "not set"]}, pluck="name"):
		frappe.db.set_value("Company", company, "default_holiday_list", name)
