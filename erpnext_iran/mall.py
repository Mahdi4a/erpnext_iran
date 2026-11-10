"""Running a mall: units, leases, and the monthly rent invoice.

A lease gives a unit to a tenant between two dates for a monthly rent that rises by a percentage on every
anniversary, plus a service charge per square metre. The invoice of a Jalali month is made once (the invoice
carries the lease and the month, and a month already invoiced is skipped), for the days of the lease inside that
month. A lease can also take a share of the tenant's sales above the base rent; that is a second, separate invoice
made after the month, when the sales are known."""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today
from iran_base.utils.jalali import is_jalali_leap, jalali_to_gregorian, to_jalali

RENT_ITEM, SERVICE_ITEM, TURNOVER_ITEM = "MALL-RENT", "MALL-SERVICE", "MALL-TURNOVER"


# ------------------------------------------------------------------ Jalali months


def days_in_month(year: int, month: int) -> int:
	if month <= 6:
		return 31
	if month <= 11:
		return 30
	return 30 if is_jalali_leap(year) else 29


def period_of(date) -> tuple[int, int]:
	year, month, _day = to_jalali(getdate(date))
	return year, month


def period_dates(year: int, month: int) -> tuple[datetime.date, datetime.date]:
	start = datetime.date(*jalali_to_gregorian(year, month, 1))
	return start, start + datetime.timedelta(days=days_in_month(year, month) - 1)


def previous_period(year: int, month: int) -> tuple[int, int]:
	return (year - 1, 12) if month == 1 else (year, month - 1)


def period_key(year: int, month: int, kind: str = "rent") -> str:
	return f"{year}-{month:02d}" + ("-T" if kind == "turnover" else "")


# ------------------------------------------------------------------ what a lease costs in a month


def effective_end(lease) -> datetime.date:
	end = getdate(lease.end_date)
	return min(end, getdate(lease.terminated_on)) if lease.get("terminated_on") else end


def years_in(lease, year: int, month: int) -> int:
	"""Anniversaries of the lease start passed by the beginning of the month (counted in Jalali months)."""
	start_year, start_month = period_of(lease.start_date)
	return max(((year * 12 + month) - (start_year * 12 + start_month)) // 12, 0)


def covered_share(lease, year: int, month: int) -> tuple[int, int]:
	"""(days of the lease inside the month, days of the month)."""
	first, last = period_dates(year, month)
	begin, end = max(getdate(lease.start_date), first), min(effective_end(lease), last)
	return max((end - begin).days + 1, 0), days_in_month(year, month)


def charges_for(lease, year: int, month: int) -> dict:
	"""Rent and service charge for the month, for the days the lease covers (zero when it covers none)."""
	days, whole = covered_share(lease, year, month)
	if not days:
		return {"rent": 0.0, "service": 0.0, "days": 0, "days_in_month": whole, "years": 0, "full_rent": 0.0}
	years = years_in(lease, year, month)
	full_rent = flt(lease.monthly_rent) * (1 + flt(lease.annual_increase_percent) / 100) ** years
	share = days / whole
	return {
		"rent": round(full_rent * share),
		"service": round(flt(lease.service_charge_per_m2) * flt(lease.area) * share),
		"days": days,
		"days_in_month": whole,
		"years": years,
		"full_rent": round(full_rent),
	}


def turnover_rent(lease, year: int, month: int) -> dict | None:
	"""The share of the month's sales above the base rent; None when there is no turnover rent or no figure yet."""
	if flt(lease.turnover_percent) <= 0:
		return None
	sales = frappe.db.get_value("Mall Turnover", {"lease": lease.name, "jalali_year": year, "jalali_month": month}, "turnover")
	if sales is None:
		return None
	base = charges_for(lease, year, month)["rent"]
	share = flt(sales) * flt(lease.turnover_percent) / 100
	return {"turnover": flt(sales), "share": round(share), "base": base, "amount": max(round(share - base), 0)}


# ------------------------------------------------------------------ the lease document


def validate_lease(doc):
	if getdate(doc.end_date) < getdate(doc.start_date):
		frappe.throw(_("The lease ends before it starts"))
	if flt(doc.monthly_rent) <= 0:
		frappe.throw(_("The monthly rent must be more than zero"))
	for field, label in (("annual_increase_percent", _("Yearly Increase")), ("turnover_percent", _("Turnover Rent"))):
		if not 0 <= flt(doc.get(field)) <= 100:
			frappe.throw(_("{0} must be between 0 and 100").format(label))
	if doc.get("invoice_day") and not 1 <= cint(doc.invoice_day) <= 28:
		frappe.throw(_("The invoice day is a day from 1 to 28"))
	unit = frappe.db.get_value("Mall Unit", doc.unit, ["company", "status"], as_dict=True)
	if not unit:
		frappe.throw(_("Unit {0} does not exist").format(doc.unit))
	if unit.status == "Maintenance":
		frappe.throw(_("Unit {0} is under maintenance").format(doc.unit))
	clash = overlapping_lease(doc)
	if clash:
		frappe.throw(_("Unit {0} is leased by {1} in those dates").format(doc.unit, clash))
	doc.status = lease_status(doc)


def overlapping_lease(doc) -> str | None:
	for other in frappe.get_all(
		"Mall Lease",
		{"unit": doc.unit, "docstatus": 1, "name": ["!=", doc.name or ""]},
		["name", "start_date", "end_date", "terminated_on"],
	):
		other_end = min(getdate(other.end_date), getdate(other.terminated_on)) if other.terminated_on else getdate(other.end_date)
		if getdate(doc.start_date) <= other_end and getdate(other.start_date) <= effective_end(doc):
			return other.name
	return None


def lease_status(doc, on=None) -> str:
	on = getdate(on or today())
	if doc.docstatus == 2:
		return "Cancelled"
	if doc.docstatus == 0:
		return "Draft"
	if doc.get("terminated_on") and getdate(doc.terminated_on) <= on:
		return "Terminated"
	if on < getdate(doc.start_date):
		return "Upcoming"
	return "Expired" if on > getdate(doc.end_date) else "Active"


def sync_unit(unit: str):
	"""The unit is leased while a lease covers today. A unit under maintenance is left as it is."""
	if frappe.db.get_value("Mall Unit", unit, "status") == "Maintenance":
		return
	current = None
	for lease in frappe.get_all("Mall Lease", {"unit": unit, "docstatus": 1}, ["name", "start_date", "end_date", "terminated_on"], order_by="start_date"):
		if getdate(lease.start_date) <= getdate(today()) <= (min(getdate(lease.end_date), getdate(lease.terminated_on)) if lease.terminated_on else getdate(lease.end_date)):
			current = lease.name
	frappe.db.set_value("Mall Unit", unit, {"status": "Leased" if current else "Vacant", "current_lease": current}, update_modified=False)


def on_lease_change(doc, method=None):
	doc.db_set("status", lease_status(doc), update_modified=False)
	sync_unit(doc.unit)


@frappe.whitelist(methods=["POST"])
def terminate_lease(lease: str, on_date: str | None = None) -> str:
	"""Ends a lease early. Nothing already invoiced is touched; from the date on, nothing is invoiced."""
	doc = frappe.get_doc("Mall Lease", lease)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted lease can be terminated"))
	when = getdate(on_date or today())
	if when < getdate(doc.start_date) or when > getdate(doc.end_date):
		frappe.throw(_("The termination date must be inside the lease"))
	frappe.db.set_value("Mall Lease", lease, "terminated_on", when, update_modified=True)
	doc.reload()
	on_lease_change(doc)
	return doc.status


def refresh_statuses():
	"""Daily: leases that have started, ended or been terminated change status, and units follow."""
	for lease in frappe.get_all("Mall Lease", {"docstatus": 1}, ["name", "unit", "status"]):
		doc = frappe.get_doc("Mall Lease", lease.name)
		new = lease_status(doc)
		if new != lease.status:
			doc.db_set("status", new, update_modified=False)
		sync_unit(lease.unit)


# ------------------------------------------------------------------ invoices


def settings():
	return frappe.get_single("Mall Settings")


def ensure_items(config=None) -> dict:
	"""The three service items rent invoices use; made when missing and remembered in Mall Settings."""
	config = config or settings()
	names = {"rent_item": (RENT_ITEM, "اجاره"), "service_item": (SERVICE_ITEM, "شارژ"), "turnover_item": (TURNOVER_ITEM, "اجاره‌ی درصدی از فروش")}
	changed = False
	for field, (code, label) in names.items():
		if config.get(field):
			continue
		if not frappe.db.exists("Item", code):
			group = "Services" if frappe.db.exists("Item Group", "Services") else frappe.db.get_value("Item Group", {"is_group": 0}, "name")
			item = frappe.new_doc("Item")
			item.update({"item_code": code, "item_name": label, "item_group": group, "stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1})
			item.flags.ignore_permissions = True
			item.insert()
		config.set(field, code)
		changed = True
	if changed:
		config.flags.ignore_permissions = True
		config.save()
	return {field: config.get(field) for field in names}


def month_text(year: int, month: int) -> str:
	names = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
	return f"{names[month - 1]} {year}"


def invoice_exists(lease: str, key: str) -> str | None:
	return frappe.db.get_value("Sales Invoice", {"mall_lease": lease, "mall_period": key, "docstatus": ["<", 2]}, "name")


def build_invoice(lease, year: int, month: int, kind: str = "rent"):
	"""The Sales Invoice of one lease for one month; None when the month is already invoiced or there is nothing to bill."""
	key = period_key(year, month, kind)
	if invoice_exists(lease.name, key):
		return None
	config = settings()
	items = ensure_items(config)
	unit = frappe.db.get_value("Mall Unit", lease.unit, ["unit_code", "floor", "cost_center"], as_dict=True)
	where = f"{unit.unit_code}" + (f" ({unit.floor})" if unit.floor else "")
	lines = []
	if kind == "rent":
		charge = charges_for(lease, year, month)
		if charge["rent"] > 0:
			note = "" if charge["days"] == charge["days_in_month"] else f" — {charge['days']}/{charge['days_in_month']}"
			lines.append((items["rent_item"], f"اجاره‌ی واحد {where}، {month_text(year, month)}{note}", charge["rent"]))
		if charge["service"] > 0:
			lines.append((items["service_item"], f"شارژ واحد {where}، {month_text(year, month)}", charge["service"]))
	else:
		extra = turnover_rent(lease, year, month)
		if extra and extra["amount"] > 0:
			lines.append((items["turnover_item"], f"اجاره‌ی درصدی واحد {where}، {month_text(year, month)} ({flt(lease.turnover_percent):g}٪ از فروش)", extra["amount"]))
	if not lines:
		return None

	doc = frappe.new_doc("Sales Invoice")
	doc.update(
		{
			"company": lease.company,
			"customer": lease.tenant,
			"posting_date": today(),
			"set_posting_time": 0,
			"update_stock": 0,
			"currency": frappe.get_cached_value("Company", lease.company, "default_currency"),
			"mall_lease": lease.name,
			"mall_period": key,
			"remarks": f"{lease.name} — {month_text(year, month)}",
		}
	)
	for item, description, amount in lines:
		doc.append("items", {"item_code": item, "description": description, "qty": 1, "rate": amount, **({"cost_center": unit.cost_center} if unit.cost_center else {})})
	if config.tax_template:
		doc.taxes_and_charges = config.tax_template
	doc.flags.ignore_permissions = True
	doc.insert()
	if cint(config.auto_submit_invoices):
		doc.submit()
	return doc


def billable_leases(year: int, month: int):
	first, last = period_dates(year, month)
	for row in frappe.get_all("Mall Lease", {"docstatus": 1, "start_date": ["<=", last], "end_date": [">=", first]}, pluck="name"):
		lease = frappe.get_doc("Mall Lease", row)
		if lease_status(lease, last) != "Cancelled" and covered_share(lease, year, month)[0] > 0:
			yield lease


@frappe.whitelist(methods=["POST"])
def generate_invoices(jalali_year: int, jalali_month: int, kind: str = "rent") -> dict:
	"""Invoices for every lease for a Jalali month. Months already invoiced are skipped, so it can be run again."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	return bill_period(cint(jalali_year), cint(jalali_month), kind)


def bill_period(year: int, month: int, kind: str = "rent", only_due: bool = False) -> dict:
	if not 1 <= month <= 12 or kind not in ("rent", "turnover"):
		frappe.throw(_("Not a month of the Jalali year"))
	made, skipped = [], 0
	default_day = cint(settings().default_invoice_day) or 1
	today_day = to_jalali(getdate(today()))[2]
	for lease in billable_leases(year, month):
		if only_due and cint(lease.invoice_day or default_day) > today_day and period_of(today()) == (year, month):
			continue
		doc = build_invoice(lease, year, month, kind)
		if doc:
			made.append(doc.name)
		else:
			skipped += 1
	return {"period": period_key(year, month, kind), "made": made, "skipped": skipped}


def bill_due_leases():
	"""Daily: this month's rent invoices for the leases whose invoice day has come, and last month's turnover rent
	where the tenant's sales have been entered."""
	if not frappe.db.exists("DocType", "Mall Lease") or not frappe.db.count("Mall Lease", {"docstatus": 1}):
		return
	year, month = period_of(today())
	bill_period(year, month, "rent", only_due=True)
	last_year, last_month = previous_period(year, month)
	bill_period(last_year, last_month, "turnover")
