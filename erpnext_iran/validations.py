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
	_sync_province(doc)
	value = _clean(doc, "pincode")
	if value and not validators.is_valid_postal_code(value):
		frappe.throw(_("Postal Code is not valid"), title=_("Invalid Address"))


def _sync_province(doc):
	"""The province is chosen from a list and written to State/Province, which the address print and
	every report already read. An address typed with a state only gets the province when it is one."""
	from erpnext_iran.fields import PROVINCES

	if doc.get("iran_province"):
		doc.set("state", doc.get("iran_province"))
	elif doc.get("state") in PROVINCES:
		doc.set("iran_province", doc.get("state"))
	if doc.get("iran_city"):
		doc.set("city", doc.get("iran_city"))
	elif doc.get("city"):
		doc.set("iran_city", doc.get("city"))


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
		_match_bank(doc, value)


def _match_bank(doc, sheba: str):
	"""A Sheba says which bank holds the account: fill the bank in when it is empty, warn when it differs."""
	from erpnext_iran.banks import bank_for_sheba, sheba_bank_code

	bank = bank_for_sheba(sheba)
	if not bank:
		return
	if not doc.get("bank"):
		doc.set("bank", bank)
	elif doc.get("bank") != bank:
		frappe.msgprint(
			_("The bank code {0} of this Sheba belongs to {1}, not {2}").format(
				sheba_bank_code(sheba), bank, doc.get("bank")
			),
			indicator="orange",
			alert=True,
		)
