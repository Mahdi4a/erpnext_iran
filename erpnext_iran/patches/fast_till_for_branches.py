import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_iran.branches import FAST_TILL
from erpnext_iran.fields import CUSTOM_FIELDS


def execute():
	"""Branches made before the quick-payment options existed get them, once. The receipt format is set only
	when the profile has none."""
	create_custom_fields({"POS Profile": CUSTOM_FIELDS["POS Profile"]}, update=True)
	for profile in frappe.get_all("Store Branch", pluck="pos_profile"):
		if not (profile and frappe.db.exists("POS Profile", profile)):
			continue
		for fieldname, value in FAST_TILL.items():
			if fieldname == "print_format" and frappe.db.get_value("POS Profile", profile, fieldname):
				continue
			frappe.db.set_value("POS Profile", profile, fieldname, value)
