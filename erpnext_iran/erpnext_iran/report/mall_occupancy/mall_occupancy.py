"""How full the mall is, by floor and as a whole, by number of units and by floor area."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "floor", "label": _("Floor"), "fieldtype": "Data", "width": 110},
		{"fieldname": "units", "label": _("Units"), "fieldtype": "Int", "width": 70},
		{"fieldname": "leased", "label": _("Leased"), "fieldtype": "Int", "width": 70},
		{"fieldname": "vacant", "label": _("Vacant"), "fieldtype": "Int", "width": 70},
		{"fieldname": "maintenance", "label": _("Maintenance"), "fieldtype": "Int", "width": 90},
		{"fieldname": "area", "label": _("Area (m²)"), "fieldtype": "Float", "width": 90},
		{"fieldname": "leased_area", "label": _("Leased Area (m²)"), "fieldtype": "Float", "width": 110},
		{"fieldname": "by_units", "label": _("Occupancy % (units)"), "fieldtype": "Percent", "width": 120},
		{"fieldname": "by_area", "label": _("Occupancy % (area)"), "fieldtype": "Percent", "width": 120},
	]


def percent(part: float, whole: float) -> float:
	return part / whole * 100 if whole else 0.0


def line(label, rows):
	units, leased = len(rows), sum(1 for r in rows if r.status == "Leased")
	area = sum(flt(r.area) for r in rows)
	leased_area = sum(flt(r.area) for r in rows if r.status == "Leased")
	return {
		"floor": label,
		"units": units,
		"leased": leased,
		"vacant": sum(1 for r in rows if r.status == "Vacant"),
		"maintenance": sum(1 for r in rows if r.status == "Maintenance"),
		"area": area,
		"leased_area": leased_area,
		# a unit under maintenance cannot be let, so it is not counted against the mall
		"by_units": percent(leased, units - sum(1 for r in rows if r.status == "Maintenance")),
		"by_area": percent(leased_area, area - sum(flt(r.area) for r in rows if r.status == "Maintenance")),
	}


def get_data(filters):
	units = frappe.get_all("Mall Unit", {"company": filters.company}, ["name", "floor", "area", "status"])
	floors: dict[str, list] = {}
	for unit in units:
		floors.setdefault(unit.floor or _("No floor"), []).append(unit)
	rows = [line(floor, members) for floor, members in sorted(floors.items())]
	if len(rows) > 1:
		rows.append(line(_("Whole mall"), units))
	return rows
