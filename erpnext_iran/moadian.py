"""Moadian (سامانه مؤدیان) e-invoice payload, data model only.

NOTHING HERE IS VERIFIED against the official Moadian documentation. The field names (inty, inp,
tins, sstid, ...) and the code lists follow the public description as remembered. There is no tax
ID generation, no signing, no encryption and no call to the tax authority: that needs the official
documents and credentials, which the project does not have. Treat `build_payload` as a draft to
compare against the official specification before any use.

Assumptions that need an owner decision (listed in the README):
	* Amounts are whole Rials. A company in IRT is multiplied by 10.
	* One VAT rate for the whole invoice, taken from the first tax row of the invoice.
	* The invoice time is the posting date and time in Tehran, sent as Unix milliseconds.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from iran_base.utils.numbers import to_latin_digits

TEHRAN = ZoneInfo("Asia/Tehran")
RIAL_PER_TOMAN = 10
UNVERIFIED = True


def rial_factor(currency: str | None) -> int:
	return RIAL_PER_TOMAN if currency == "IRT" else 1


def to_millis(posting_date, posting_time=None) -> int:
	"""Unix milliseconds of a date and an optional time, read as Tehran time."""
	if isinstance(posting_date, str):
		posting_date = datetime.date.fromisoformat(posting_date[:10])
	if isinstance(posting_time, datetime.timedelta):
		time = (datetime.datetime.min + posting_time).time()
	elif isinstance(posting_time, str) and posting_time:
		time = datetime.time.fromisoformat(posting_time.split(".")[0])
	elif isinstance(posting_time, datetime.time):
		time = posting_time
	else:
		time = datetime.time(0, 0)
	moment = datetime.datetime.combine(posting_date, time, tzinfo=TEHRAN)
	return int(moment.timestamp() * 1000)


def _amount(value, factor: int) -> int:
	return int(round((value or 0) * factor))


def vat_rate(invoice) -> float:
	"""The rate of the first tax row. A different rate per item is not supported yet."""
	for row in invoice.get("taxes") or []:
		if row.get("rate"):
			return float(row.rate)
	return 0.0


def missing_data(invoice, seller: dict, buyer: dict, items: dict, units: dict) -> list[str]:
	"""What has to be filled before a payload makes sense. Empty list means nothing is missing."""
	missing = []
	if not seller.get("economic_code"):
		missing.append(_("Seller economic code (Company, Tax ID)"))
	if not seller.get("memory_id"):
		missing.append(_("Seller tax memory ID (Company)"))
	if not (buyer.get("economic_code") or buyer.get("national_id") or buyer.get("legal_id")):
		missing.append(_("Buyer economic code, national ID or legal ID (Customer)"))
	for row in invoice.get("items") or []:
		if not items.get(row.item_code):
			missing.append(_("Goods or service ID of item {0}").format(row.item_code))
		if not units.get(row.uom):
			missing.append(_("Moadian unit code of UOM {0}").format(row.uom))
	return missing


def build_payload(invoice, seller: dict, buyer: dict, items: dict, units: dict) -> dict:
	"""{"header": {...}, "body": [...], "payments": []} for one Sales Invoice. Unverified, see the module doc.

	`seller`: economic_code, memory_id. `buyer`: economic_code, national_id, legal_id.
	`items`: item code -> goods or service ID. `units`: UOM -> Moadian unit code.
	"""
	factor = rial_factor(invoice.get("currency"))
	rate = vat_rate(invoice)

	body = []
	total_before_discount = total_discount = total_after_discount = total_vat = 0
	for row in invoice.get("items") or []:
		before = _amount(row.get("rate", 0) * row.get("qty", 0), factor)
		discount = _amount((row.get("discount_amount") or 0) * row.get("qty", 0), factor)
		after = before - discount
		vat = int(round(after * rate / 100))
		body.append(
			{
				"sstid": items.get(row.item_code, ""),
				"sstt": row.get("item_name") or row.item_code,
				"am": row.get("qty", 0),
				"mu": units.get(row.uom, ""),
				"fee": _amount(row.get("rate", 0), factor),
				"prdis": before,
				"dis": discount,
				"adis": after,
				"vra": rate,
				"vam": vat,
				"tsstam": after + vat,
			}
		)
		total_before_discount += before
		total_discount += discount
		total_after_discount += after
		total_vat += vat

	buyer_id = to_latin_digits(buyer.get("national_id") or buyer.get("legal_id") or "")
	header = {
		"taxid": invoice.get("moadian_tax_id") or "",
		"indatim": to_millis(invoice.posting_date, invoice.get("posting_time")),
		"inty": int(invoice.get("moadian_invoice_type") or 1),
		"inno": invoice.get("name"),
		"inp": int(invoice.get("moadian_pattern") or 1),
		"ins": int(invoice.get("moadian_subject") or 1),
		"tins": to_latin_digits(seller.get("economic_code") or ""),
		"tob": int(invoice.get("moadian_buyer_type") or 2),
		"bid": buyer_id,
		"tinb": to_latin_digits(buyer.get("economic_code") or ""),
		"setm": int(invoice.get("moadian_settlement_method") or 1),
		"tprdis": total_before_discount,
		"tdis": total_discount,
		"tadis": total_after_discount,
		"tvam": total_vat,
		"tbill": total_after_discount + total_vat,
	}
	return {"header": header, "body": body, "payments": [], "unverified": UNVERIFIED}


@frappe.whitelist()
def get_payload(invoice_name: str) -> dict:
	"""The draft payload of a Sales Invoice, for review. It is not sent anywhere."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("read")

	company = frappe.get_cached_doc("Company", invoice.company)
	seller = {"economic_code": company.tax_id, "memory_id": company.get("moadian_memory_id")}
	buyer = frappe.db.get_value(
		"Customer", invoice.customer, ["national_id", "legal_id", "economic_code"], as_dict=True
	)
	items = {
		row.item_code: frappe.db.get_value("Item", row.item_code, "moadian_sstid") for row in invoice.items
	}
	units = {row.uom: frappe.db.get_value("UOM", row.uom, "moadian_unit_code") for row in invoice.items}

	return {
		"payload": build_payload(invoice, seller, buyer or {}, items, units),
		"missing": missing_data(invoice, seller, buyer or {}, items, units),
	}
