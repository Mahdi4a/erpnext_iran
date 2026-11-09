"""The pharmacy pack: what the law asks of a drug sale.

A prescription-only drug is not sold without the prescription number and who wrote it. A controlled drug also
needs the patient's name and a valid national ID, and goes in the Prescription Register. A drug has an approved
retail price, and a sale above it is refused. Drugs with the same generic name can stand in for each other.
Batches and expiry dates are the food pack's (the same Stock Settings).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def drug_flags(item_codes) -> dict[str, dict]:
	"""{item_code: {requires_prescription, is_controlled_drug, approved_price, item_name}} for the flagged ones."""
	codes = list({c for c in item_codes if c})
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", codes]},
		fields=["name", "item_name", "requires_prescription", "is_controlled_drug", "approved_price"],
	)
	return {
		row.name: row
		for row in rows
		if row.requires_prescription or row.is_controlled_drug or flt(row.approved_price) > 0
	}


def validate_sale(doc, method=None):
	"""Sales Invoice before_submit. Returns are not checked: giving a drug back asks nothing of the patient."""
	if doc.get("is_return"):
		return
	flags = drug_flags([row.item_code for row in doc.get("items") or []])
	if not flags:
		return

	over = []
	for row in doc.items:
		cap = flt((flags.get(row.item_code) or {}).get("approved_price"))
		per_unit = flt(row.rate) / (flt(row.get("conversion_factor")) or 1)
		if cap > 0 and per_unit > cap + 0.5:
			over.append(f"{row.item_name or row.item_code}: {per_unit:,.0f} > {cap:,.0f}")
	if over:
		frappe.throw(
			_("A drug cannot be sold above its approved price:") + "<br>" + "<br>".join(over),
			title=_("Approved Price"),
		)

	prescribed = [r.item_name or r.item_code for r in doc.items if (flags.get(r.item_code) or {}).get("requires_prescription")]
	controlled = [r.item_name or r.item_code for r in doc.items if (flags.get(r.item_code) or {}).get("is_controlled_drug")]
	if (prescribed or controlled) and not ((doc.get("prescription_no") or "").strip() and (doc.get("prescriber_name") or "").strip()):
		frappe.throw(
			_("Needs a prescription: {0}. Fill in the prescription number and the prescriber.").format("، ".join(prescribed + controlled)),
			title=_("Prescription Needed"),
		)
	if controlled:
		from iran_base.utils.validators import is_valid_national_id

		if not (doc.get("patient_name") or "").strip() or not is_valid_national_id(doc.get("patient_national_id")):
			frappe.throw(
				_("A controlled drug ({0}) needs the patient's name and a valid national ID.").format("، ".join(controlled)),
				title=_("Patient Needed"),
			)


@frappe.whitelist()
def rx_requirements(item_codes) -> dict:
	"""What a basket of items asks of the sale, for the POS to collect it before payment."""
	frappe.has_permission("Item", "read", throw=True)
	codes = frappe.parse_json(item_codes) if isinstance(item_codes, str) else item_codes
	flags = drug_flags(codes or [])
	return {
		"prescription": [c for c, f in flags.items() if f.requires_prescription or f.is_controlled_drug],
		"controlled": [c for c, f in flags.items() if f.is_controlled_drug],
		"names": {c: f.item_name for c, f in flags.items()},
	}


@frappe.whitelist()
def alternatives(item_code: str) -> list[dict]:
	"""Other drugs with the same generic name (and strength and form when the item has them), the ones with
	stock first, then the cheapest. For the pharmacist whose shelf has run out."""
	frappe.has_permission("Item", "read", item_code, throw=True)
	generic = (frappe.db.get_value("Item", item_code, "generic_name") or "").strip()
	if not generic:
		frappe.throw(_("{0} has no generic name").format(item_code))
	original = frappe.db.get_value("Item", item_code, ["drug_strength", "dosage_form"], as_dict=True)
	rows = frappe.get_all(
		"Item",
		filters={"generic_name": generic, "name": ["!=", item_code], "disabled": 0},
		fields=["name", "item_name", "drug_strength", "dosage_form", "requires_prescription", "approved_price"],
	)
	stock = dict(
		frappe.db.sql(
			"select item_code, sum(actual_qty) from `tabBin` where item_code in %s group by item_code",
			(tuple(r.name for r in rows) or ("",),),
		)
	)
	price = {
		r.item_code: r.price_list_rate
		for r in frappe.get_all("Item Price", {"item_code": ["in", [r.name for r in rows] or [""]], "selling": 1}, ["item_code", "price_list_rate"])
	}
	result = [
		{
			"item_code": r.name,
			"item_name": r.item_name,
			"strength": r.drug_strength or "",
			"form": r.dosage_form or "",
			"same_strength": int((r.drug_strength or "") == (original.drug_strength or "")),
			"same_form": int((r.dosage_form or "") == (original.dosage_form or "")),
			"stock": flt(stock.get(r.name)),
			"price": flt(price.get(r.name)) or flt(r.approved_price),
		}
		for r in rows
	]
	result.sort(key=lambda r: (r["stock"] <= 0, -r["same_strength"], -r["same_form"], r["price"] or 1e18))
	return result
