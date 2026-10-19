from __future__ import annotations

import frappe
from frappe import _
from iran_base.utils import validators
from iran_base.utils.numbers import to_latin_digits


def _clean(doc, fieldname: str) -> str:
	"""The value with Persian digits turned into 0-9, written back so it is stored the same way."""
	value = to_latin_digits(doc.get(fieldname) or "").strip()
	if value != (doc.get(fieldname) or ""):
		doc.set(fieldname, value)
	return value


def validate_party(doc, method=None):
	"""Customer and Supplier. Empty is allowed; a value that is given must be a real identifier."""
	checks = (
		("national_id", validators.is_valid_national_id, _("National ID is not valid")),
		("legal_id", validators.is_valid_legal_id, _("Legal ID is not valid")),
		("economic_code", validators.is_valid_economic_code, _("Economic Code must be 12 or 14 digits")),
	)
	for fieldname, is_valid, message in checks:
		value = _clean(doc, fieldname)
		if value and not is_valid(value):
			frappe.throw(message, title=_("Invalid Iran Tax Identifier"))


def validate_address(doc, method=None):
	if doc.get("country") != "Iran":
		return
	value = _clean(doc, "pincode")
	if value and not validators.is_valid_postal_code(value):
		frappe.throw(_("Postal Code is not valid"), title=_("Invalid Address"))
