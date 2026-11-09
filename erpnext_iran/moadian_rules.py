"""Value rules of RC_IITP.IS_V7.9 section 8 that the tax authority checks and that can be checked
before sending: identity lengths, the invoice date, quantities and prices. Plain English messages."""

from __future__ import annotations

import time

# Length of the buyer ID by buyer type: real 10 (national number), legal 11 (national ID),
# civil partnership 11, foreign national 12 (v7.9 table 11)
BUYER_ID_LENGTH = {1: 10, 2: 11, 3: 11, 4: 12}
SINGLE_ITEM_PATTERNS = (6, 8)  # an air ticket and a waybill carry one unit per row
BUYER_OPTIONAL_PATTERNS = (7, 11)  # export and bourse need no buyer in a type 1 invoice


def _is_economic_code(value) -> bool:
	return str(value).isdigit() and len(str(value)) in (11, 14)


def seller_problems(header: dict) -> list[str]:
	if not _is_economic_code(header.get("tins", "")):
		return ["The economic code of the company (Tax ID) must be 11 or 14 digits"]
	return []


def buyer_problems(header: dict) -> list[str]:
	problems = []
	buyer_type, buyer_id, economic = header.get("tob"), header.get("bid", ""), header.get("tinb", "")
	if economic and not _is_economic_code(economic):
		problems.append("The economic code of the buyer must be 11 or 14 digits")
	wanted = BUYER_ID_LENGTH.get(buyer_type)
	if buyer_id and wanted and not (str(buyer_id).isdigit() and len(str(buyer_id)) == wanted):
		problems.append(f"The buyer ID must be {wanted} digits for this type of buyer")
	if header.get("inty") != 1 or header.get("inp") in BUYER_OPTIONAL_PATTERNS:
		return problems
	if buyer_type in (2, 3) and not economic:
		problems.append("A legal buyer needs an economic code")
	if buyer_type in (1, 4) and not (buyer_id or economic):
		problems.append("A real or foreign buyer needs a national number or an economic code")
	if buyer_type in (1, 4) and not header.get("bpc"):
		problems.append("A real or foreign buyer needs a postal code (Address of the customer)")
	return problems


def row_problems(payload: dict) -> list[str]:
	problems = []
	for number, line in enumerate(payload["body"], start=1):
		if not (str(line.get("sstid", "")).isdigit() and len(str(line["sstid"])) == 13):
			problems.append(f"Row {number}: the goods or service ID must be 13 digits")
		if line.get("am", 0) <= 0:
			problems.append(f"Row {number}: the quantity must be above zero")
		if payload["header"].get("inp") in SINGLE_ITEM_PATTERNS and line.get("am") != 1:
			problems.append(f"Row {number}: this pattern allows a quantity of 1 only")
		if not 0 <= line.get("vra", 0) < 1000:
			problems.append(f"Row {number}: the VAT rate must be between 0 and 999")
	return problems


def data_problems(payload: dict, now_millis: int | None = None) -> list[str]:
	"""Everything the tax authority would refuse that we can see now, in one list."""
	header = payload["header"]
	problems = seller_problems(header) + buyer_problems(header) + row_problems(payload)
	if header.get("ins") != 3 and header.get("tprdis", 1) <= 0:
		problems.append("The invoice total must be above zero")
	if header["indatim"] > (now_millis if now_millis is not None else int(time.time() * 1000)):
		problems.append("The invoice date and time are in the future")
	return problems
