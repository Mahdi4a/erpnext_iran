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


def iran_sheba_check_digits_ok(iban: str) -> bool:
	"""ISO 13616 mod 97 check: move the first four characters to the end, letters become 10-35."""
	rearranged = iban[4:] + iban[:4]
	number = "".join(str(int(c, 36)) for c in rearranged)
	return int(number) % 97 == 1


def normalize_sheba(value) -> str:
	"""'ir06 2960 ...' or '062960...' to 'IR062960...'. Anything else is returned cleaned up only."""
	text = to_latin_digits(value or "").replace(" ", "").replace("-", "").upper()
	if len(text) == 24 and text.isdigit():
		text = "IR" + text
	return text


def is_valid_sheba(value) -> bool:
	"""IR, two check digits and 22 digits, 26 characters in all, with a valid mod 97 check."""
	text = normalize_sheba(value)
	return len(text) == 26 and text.startswith("IR") and text[2:].isdigit() and iran_sheba_check_digits_ok(text)


def validate_bank_account(doc, method=None):
	"""Iranian Sheba numbers (IR...) are checked here. Another country's IBAN is left alone."""
	value = normalize_sheba(doc.get("iban"))
	if not value:
		return
	if value.startswith("IR"):
		if not is_valid_sheba(value):
			frappe.throw(_("Sheba (IBAN) is not valid"), title=_("Invalid Bank Account"))
		doc.set("iban", value)
