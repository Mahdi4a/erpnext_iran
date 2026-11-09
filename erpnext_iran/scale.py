"""Barcodes printed by a shop scale for loose goods (fruit, meat, nuts, cheese).

A label is an EAN-13: a prefix (2 by default), the PLU of the item, the weight or the price, and the check
digit. The same item has a different code on every label, so it cannot be registered as one barcode. The item
carries its PLU instead, and gets one ordinary barcode made of the prefix, the PLU and zeros for the value.
The POS reads a scanned label, finds the item by that barcode, and takes the quantity from the value."""

from __future__ import annotations

import frappe
from frappe import _

DEFAULTS = {
	"prefix": "2",
	"plu_digits": 6,
	"value_digits": 5,
	"mode": "Weight",
	"weight_divisor": 1000,
}


def get_scale_settings() -> dict:
	from iran_base.settings import get_setting

	def read(key, default):
		return get_setting(key, "ERPNext Iran Settings") or default

	return {
		"prefix": str(read("scale_barcode_prefix", DEFAULTS["prefix"])),
		"plu_digits": int(read("scale_plu_digits", DEFAULTS["plu_digits"])),
		"value_digits": int(read("scale_value_digits", DEFAULTS["value_digits"])),
		"mode": read("scale_value_mode", DEFAULTS["mode"]),
		"weight_divisor": float(read("scale_weight_divisor", DEFAULTS["weight_divisor"])),
	}


def ean13_check_digit(first_twelve: str) -> str:
	total = sum(int(d) * (3 if index % 2 else 1) for index, d in enumerate(first_twelve))
	return str((10 - total % 10) % 10)


def item_barcode(plu: str, settings: dict | None = None) -> str:
	"""The barcode an item with this PLU is registered under: prefix, PLU, zeros, check digit."""
	settings = settings or get_scale_settings()
	body = settings["prefix"] + plu + "0" * settings["value_digits"]
	if len(body) != 12:
		frappe.throw(
			_("The prefix, PLU and value digits of the scale barcode must add up to 12, not {0}.").format(len(body))
		)
	return body + ean13_check_digit(body)


def parse_label(code: str, settings: dict | None = None) -> dict | None:
	"""A scanned scale label as {"barcode": the item's barcode, "value": the number on the label}, or None when
	the code is not a scale label."""
	settings = settings or get_scale_settings()
	prefix = settings["prefix"]
	if len(code) != 13 or not code.isdigit() or not code.startswith(prefix):
		return None
	if ean13_check_digit(code[:12]) != code[12]:
		return None

	start = len(prefix)
	plu = code[start : start + settings["plu_digits"]]
	value = int(code[start + settings["plu_digits"] : 12])
	return {"barcode": item_barcode(plu, settings), "value": value}


def validate_item(doc, method=None):
	"""Keeps the barcode of the item in step with its PLU."""
	plu = (doc.get("scale_plu") or "").strip()
	settings = get_scale_settings()
	before = doc.get_doc_before_save()
	old_plu = (before.get("scale_plu") or "").strip() if before else ""

	if old_plu and old_plu != plu and len(old_plu) == settings["plu_digits"]:
		stale = item_barcode(old_plu, settings)
		doc.barcodes = [row for row in doc.barcodes if row.barcode != stale]

	if not plu:
		return

	if not plu.isdigit() or len(plu) != settings["plu_digits"]:
		frappe.throw(_("The PLU of the scale must be {0} digits.").format(settings["plu_digits"]))

	other = frappe.db.get_value("Item", {"scale_plu": plu, "name": ["!=", doc.name]})
	if other:
		frappe.throw(_("PLU {0} already belongs to item {1}.").format(plu, other))

	barcode = item_barcode(plu, settings)
	if not any(row.barcode == barcode for row in doc.barcodes):
		doc.append("barcodes", {"barcode": barcode, "barcode_type": "EAN"})


def extend_bootinfo(bootinfo):
	bootinfo.erpnext_iran["scale"] = get_scale_settings()
