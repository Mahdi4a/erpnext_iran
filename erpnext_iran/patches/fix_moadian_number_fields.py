import frappe

from erpnext_iran.moadian_extras import HEADER_EXTRAS, ITEM_EXTRAS

NUMBER_TYPES = ("Int", "Float")


def execute():
	"""Some pattern fields were Data and became Int or Float. Frappe refuses that change on a site that
	already has the field, so migrate failed there. Text that is not a number becomes 0, as an empty number field is, the field is
	changed here, and the column is converted."""
	changed = set()
	for doctype, extras in (("Sales Invoice", HEADER_EXTRAS), ("Sales Invoice Item", ITEM_EXTRAS)):
		for code, _label, fieldtype, *_options in extras:
			if fieldtype not in NUMBER_TYPES:
				continue
			name = f"{doctype}-moadian_{code}"
			current = frappe.db.get_value("Custom Field", name, "fieldtype")
			column = f"moadian_{code}"
			if not current or not frappe.db.has_column(doctype, column):
				continue
			if current in NUMBER_TYPES and not is_text_column(doctype, column):
				continue

			frappe.db.sql(
				f"update `tab{doctype}` set `{column}` = 0 where `{column}` is null or `{column}` not regexp '^-?[0-9.]+$'"
			)
			frappe.db.set_value("Custom Field", name, "fieldtype", fieldtype, update_modified=False)
			changed.add(doctype)

	for doctype in changed:
		frappe.clear_cache(doctype=doctype)
		frappe.db.updatedb(doctype)


def is_text_column(doctype: str, column: str) -> bool:
	column_type = frappe.db.get_column_type(doctype, column) or ""
	return column_type.startswith(("varchar", "text", "longtext"))
