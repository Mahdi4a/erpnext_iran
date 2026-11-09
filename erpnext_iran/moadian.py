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
import json
import os
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from iran_base.utils.numbers import to_latin_digits

from erpnext_iran.moadian_extras import HEADER_CODES, ITEM_CODES

TEHRAN = ZoneInfo("Asia/Tehran")
RIAL_PER_TOMAN = 10
UNVERIFIED = True


PATTERN_FILE = os.path.join(os.path.dirname(__file__), "data", "moadian_patterns.json")


def pattern_fields(invoice_type, pattern) -> dict:
	"""Field code -> mandatory, optional or conditional, for one invoice type and pattern (v7.9 table 1)."""
	with open(PATTERN_FILE, encoding="utf8") as file:
		patterns = json.load(file)["patterns"]
	return patterns.get(str(invoice_type), {}).get(str(pattern), {})


def pattern_gaps(payload: dict) -> list[str]:
	"""Mandatory fields of the invoice's type and pattern that the payload does not carry."""
	header = payload["header"]
	spec = pattern_fields(header["inty"], header["inp"])
	if not spec:
		raise ValueError(f"Pattern {header['inp']} is not valid for invoice type {header['inty']}")
	present = set(header) | {code for row in payload["body"] for code in row}
	present |= {code for row in payload["payments"] for code in row}
	return [code for code, status in spec.items() if status == "mandatory" and code not in present]


def code_of(value, default: int = 1) -> int:
	"""The number of a Select option like "1 - Sale": the user reads the words, Moadian gets the number."""
	text = str(value or "").split("-")[0].strip()
	return int(text) if text.isdigit() else default


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
	"""The rate of the first tax row: the rate of an item that has none of its own."""
	for row in invoice.get("taxes") or []:
		if row.get("rate"):
			return float(row.rate)
	return 0.0


def row_vat_rate(row, default: float) -> float:
	"""The item's own rate (Item Tax Template: account -> rate), else the invoice's."""
	own = row.get("item_tax_rate")
	if not own:
		return default
	rates = json.loads(own) if isinstance(own, str) else own
	return float(sum(rates.values()))


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
	"""{"header": {...}, "body": [...], "payments": []} for one Sales Invoice, cut to its pattern.

	`seller`: economic_code, memory_id. `buyer`: economic_code, national_id, legal_id.
	`items`: item code -> goods or service ID. `units`: UOM -> Moadian unit code.
	"""
	factor = rial_factor(invoice.get("currency"))
	sign = -1 if invoice.get("is_return") else 1
	default_rate = vat_rate(invoice)
	body = [_body_row(row, factor, sign, default_rate, items, units) for row in invoice.get("items") or []]
	header = _header(invoice, seller, buyer, body, factor)
	payload = {"header": header, "body": body, "payments": [], "unverified": UNVERIFIED}
	return _cut_to_pattern(payload)


def _body_row(row, factor, sign, default_rate, items, units) -> dict:
	rate = row_vat_rate(row, default_rate)
	qty = sign * (row.get("qty") or 0)
	before = _amount(row.get("rate", 0) * qty, factor)
	discount = _amount((row.get("discount_amount") or 0) * qty, factor)
	after = before - discount
	vat = int(round(after * rate / 100))
	line = {
		"sstid": items.get(row.item_code, ""),
		"sstt": row.get("item_name") or row.item_code,
		"am": qty,
		"mu": units.get(row.uom, ""),
		"fee": _amount(row.get("rate", 0), factor),
		"prdis": before,
		"dis": discount,
		"adis": after,
		"vra": rate,
		"vam": vat,
		"tsstam": after + vat,
	}
	for code in ITEM_CODES:
		if row.get(f"moadian_{code}") not in (None, "", 0):
			line[code] = row.get(f"moadian_{code}")
	return line


def _header(invoice, seller, buyer, body, factor) -> dict:
	total = {code: sum(line[code] for line in body) for code in ("prdis", "dis", "adis", "vam")}
	bill = total["adis"] + total["vam"]
	paid = min(_amount(invoice.get("paid_amount"), factor), bill)
	method = code_of(invoice.get("moadian_settlement_method"), 1)
	cash, credit = {1: (bill, 0), 2: (0, bill)}.get(method, (paid, bill - paid))
	buyer_id = to_latin_digits(buyer.get("national_id") or buyer.get("legal_id") or "")
	header = {
		"taxid": invoice.get("moadian_tax_id") or "",
		"indatim": to_millis(invoice.posting_date, invoice.get("posting_time")),
		"inty": code_of(invoice.get("moadian_invoice_type"), 1),
		"inno": invoice.get("moadian_serial") or 0,
		"inp": code_of(invoice.get("moadian_pattern"), 1),
		"ins": 4 if invoice.get("is_return") else code_of(invoice.get("moadian_subject"), 1),
		"tins": to_latin_digits(seller.get("economic_code") or ""),
		"tob": code_of(invoice.get("moadian_buyer_type"), 2),
		"bid": buyer_id,
		"tinb": to_latin_digits(buyer.get("economic_code") or ""),
		"setm": method,
		"tprdis": total["prdis"],
		"tdis": total["dis"],
		"tadis": total["adis"],
		"tvam": total["vam"],
		"todam": 0,
		"tbill": bill,
		"cap": cash,
		"insp": credit,
		"irtaxid": invoice.get("moadian_reference_tax_id") or "",
	}
	for code in HEADER_CODES:
		if invoice.get(f"moadian_{code}") not in (None, "", 0):
			header[code] = invoice.get(f"moadian_{code}")
	return _add_totals(header, body)


def _add_totals(header: dict, body: list[dict]) -> dict:
	"""Header totals that are plain sums of a body field, for the patterns that ask for them."""
	for total, field in (("tonw", "nw"), ("torv", "ssrv"), ("tocv", "sscv")):
		if any(field in line for line in body):
			header[total] = sum(line.get(field, 0) for line in body)
	return header


def _cut_to_pattern(payload: dict) -> dict:
	"""Drop what the pattern ignores or what is empty: the table says such a field has no effect."""
	header = payload["header"]
	allowed = pattern_fields(header["inty"], header["inp"])
	if not allowed:
		return payload
	payload["header"] = {k: v for k, v in header.items() if k in allowed and v not in ("", None)}
	payload["body"] = [{k: v for k, v in line.items() if k in allowed} for line in payload["body"]]
	payload["header"].setdefault("taxid", "")
	return payload


def reference_tax_id(invoice) -> str:
	"""The tax ID of the invoice a return or a correction points at."""
	reference = invoice.get("return_against") if invoice.get("is_return") else None
	reference = reference or invoice.get("moadian_reference_invoice")
	return frappe.db.get_value("Sales Invoice", reference, "moadian_tax_id") or "" if reference else ""


@frappe.whitelist()
def get_payload(invoice_name: str) -> dict:
	"""The draft payload of a Sales Invoice, for review. It is not sent anywhere."""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	invoice.check_permission("read")

	invoice.moadian_reference_tax_id = reference_tax_id(invoice)
	company = frappe.get_cached_doc("Company", invoice.company)
	seller = {"economic_code": company.tax_id, "memory_id": company.get("moadian_memory_id")}
	buyer = frappe.db.get_value(
		"Customer", invoice.customer, ["national_id", "legal_id", "economic_code"], as_dict=True
	)
	items = {
		row.item_code: frappe.db.get_value("Item", row.item_code, "moadian_sstid") for row in invoice.items
	}
	units = {row.uom: frappe.db.get_value("UOM", row.uom, "moadian_unit_code") for row in invoice.items}

	payload = build_payload(invoice, seller, buyer or {}, items, units)
	missing = missing_data(invoice, seller, buyer or {}, items, units)
	try:
		gaps = pattern_gaps(payload)
	except ValueError as error:
		gaps = []
		missing.append(str(error))
	header = payload["header"]
	if header["ins"] != 1 and not header.get("irtaxid"):
		missing.append(_("The invoice this one corrects or returns has not been sent to Moadian yet"))
	missing += [_("Field {0} is mandatory for this pattern and is not filled").format(c) for c in gaps if c != "taxid"]
	return {"payload": payload, "missing": missing}
