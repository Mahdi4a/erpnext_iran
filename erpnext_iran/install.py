from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from erpnext_iran.defaults import apply_defaults
from erpnext_iran.fields import CUSTOM_FIELDS
from erpnext_iran.jalali import ensure_current_and_next_fiscal_years
from erpnext_iran.setup import ensure_vat_templates


def after_install():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	apply_defaults()
	ensure_current_and_next_fiscal_years()
	for company in frappe.get_all("Company", pluck="name"):
		ensure_vat_templates(company)


def after_migrate():
	"""Keeps the custom fields in step with this app after an update."""
	create_custom_fields(CUSTOM_FIELDS, update=True)
