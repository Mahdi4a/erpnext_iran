import frappe

from erpnext_iran.branches import DEFAULT_MODE


def execute():
	"""Branch tills made before this took cash as the default mode; the card reader is what most customers use."""
	for profile in frappe.get_all("Store Branch", pluck="pos_profile"):
		if not (profile and frappe.db.exists("POS Profile", profile)):
			continue
		rows = frappe.get_all("POS Payment Method", {"parent": profile}, ["name", "mode_of_payment"])
		if not any(row.mode_of_payment == DEFAULT_MODE for row in rows):
			continue
		for row in rows:
			frappe.db.set_value("POS Payment Method", row.name, "default", 1 if row.mode_of_payment == DEFAULT_MODE else 0)
