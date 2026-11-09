import frappe

from erpnext_iran.branches import FAST_TILL


def execute():
	"""Branches made before the quick-payment options existed get them, once. The receipt format is set only
	when the profile has none."""
	for profile in frappe.get_all("Store Branch", pluck="pos_profile"):
		if profile and frappe.db.exists("POS Profile", profile):
			for fieldname, value in FAST_TILL.items():
				if fieldname == "print_format" and frappe.db.get_value("POS Profile", profile, fieldname):
					continue
				if frappe.db.has_column("POS Profile", fieldname):
					frappe.db.set_value("POS Profile", profile, fieldname, value)
