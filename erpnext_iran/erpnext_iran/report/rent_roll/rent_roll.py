"""Every unit of the mall with who holds it and what it brings in this month."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from erpnext_iran import mall


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	money = {"fieldtype": "Currency", "width": 120}
	return [
		{"fieldname": "unit", "label": _("Unit"), "fieldtype": "Link", "options": "Mall Unit", "width": 90},
		{"fieldname": "floor", "label": _("Floor"), "fieldtype": "Data", "width": 70},
		{"fieldname": "unit_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "area", "label": _("Area (m²)"), "fieldtype": "Float", "width": 80},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "tenant", "label": _("Tenant"), "fieldtype": "Link", "options": "Customer", "width": 150},
		{"fieldname": "lease", "label": _("Lease"), "fieldtype": "Link", "options": "Mall Lease", "width": 110},
		{"fieldname": "end_date", "label": _("Lease Ends"), "fieldtype": "Date", "width": 95},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 80},
		{"fieldname": "rent", "label": _("Rent this Month"), **money},
		{"fieldname": "service", "label": _("Service Charge"), **money},
		{"fieldname": "total", "label": _("Total"), **money},
		{"fieldname": "rent_per_m2", "label": _("Rent per m²"), **money},
	]


def get_data(filters):
	conditions, values = ["unit.company = %(company)s"], {"company": filters.company}
	if filters.get("floor"):
		conditions.append("unit.floor = %(floor)s")
		values["floor"] = filters.floor
	if filters.get("status"):
		conditions.append("unit.status = %(status)s")
		values["status"] = filters.status
	units = frappe.db.sql(
		f"select name, floor, unit_type, area, status, current_lease from `tabMall Unit` unit where {' and '.join(conditions)} order by floor, name",
		values,
		as_dict=True,
	)
	year, month = mall.period_of(today())
	rows = []
	for unit in units:
		row = {"unit": unit.name, "floor": unit.floor, "unit_type": unit.unit_type, "area": flt(unit.area), "status": unit.status}
		if unit.current_lease:
			lease = frappe.get_doc("Mall Lease", unit.current_lease)
			charge = mall.charges_for(lease, year, month)
			full = round(charge["full_rent"] + flt(lease.service_charge_per_m2) * flt(lease.area))  # a whole month, not a share
			row.update(
				{
					"tenant": lease.tenant,
					"lease": lease.name,
					"end_date": mall.effective_end(lease),
					"days_left": (mall.effective_end(lease) - getdate(today())).days,
					"rent": charge["full_rent"],
					"service": round(flt(lease.service_charge_per_m2) * flt(lease.area)),
					"total": full,
					"rent_per_m2": round(charge["full_rent"] / flt(unit.area)) if flt(unit.area) else 0,
				}
			)
		rows.append(row)
	if filters.get("ending_within") not in (None, ""):
		limit = int(filters.ending_within)
		rows = [r for r in rows if r.get("lease") and 0 <= r["days_left"] <= limit]
	if rows:
		rows.append(
			{
				"unit": _("Total"),
				"area": sum(r["area"] for r in rows),
				"rent": sum(r.get("rent", 0) for r in rows),
				"service": sum(r.get("service", 0) for r in rows),
				"total": sum(r.get("total", 0) for r in rows),
			}
		)
	return rows
