"""Bring the data of the program a business used before (an accounting or POS program) into ERPNext.

The shape is the same for every source program:

    read_table      CSV or Excel file  ->  headers + rows
    auto_map        headers            ->  which column holds which field (English and Persian names)
    prepare_*       rows + mapping     ->  clean records + the problems found, row by row
    import_*        records            ->  documents in ERPNext, one savepoint per record

A source program that names its columns differently only needs more aliases (or a mapping given by hand),
no new code. Nothing here knows about a particular program.

Nothing is written by prepare_*. A problem row is left out and reported; the valid rows still go in.
Running an import twice is safe: what already exists is skipped, not changed.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from iran_base.utils import validators
from iran_base.utils.numbers import to_latin_digits

# --- reading the file -------------------------------------------------------------------------------

ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
ZERO_WIDTH = "‌‍‎‏﻿"


def clean_text(value) -> str:
	"""Cell text as it should be stored: Latin digits, Persian letters (programs often export Arabic ي and
	ك), no stray spaces."""
	if value is None:
		return ""
	text = to_latin_digits(str(value)).translate(ARABIC_TO_PERSIAN)
	for mark in "‎‏﻿":
		text = text.replace(mark, "")
	return re.sub(r"\s+", " ", text).strip()


def header_key(value) -> str:
	"""A header reduced to what identifies it: no case, spaces, half-spaces or punctuation."""
	text = clean_text(value).lower()
	for mark in ZERO_WIDTH:
		text = text.replace(mark, "")
	return re.sub(r"[\s_\-./:()]+", "", text)


def read_table(content: bytes, filename: str) -> tuple[list[str], list[dict]]:
	"""The headers and the rows (as {header: text}) of a CSV or xlsx file. Empty rows are dropped."""
	name = (filename or "").lower()
	if name.endswith((".xlsx", ".xlsm")):
		raw_rows = _xlsx_rows(content)
	elif name.endswith((".csv", ".txt", ".tsv")):
		raw_rows = _csv_rows(content)
	else:
		raise ValueError("unsupported_file")
	raw_rows = [row for row in raw_rows if any(clean_text(cell) for cell in row)]
	if not raw_rows:
		raise ValueError("empty_file")

	headers = [clean_text(cell) for cell in raw_rows[0]]
	rows = []
	for raw in raw_rows[1:]:
		cells = list(raw) + [""] * (len(headers) - len(raw))
		rows.append({header: clean_text(cell) for header, cell in zip(headers, cells) if header})
	return [header for header in headers if header], rows


def _csv_rows(content: bytes) -> list[list]:
	# Iranian programs often write CSV in Windows-1256, not UTF-8.
	for encoding in ("utf-8-sig", "cp1256"):
		try:
			text = content.decode(encoding)
			break
		except UnicodeDecodeError:
			continue
	else:
		raise ValueError("unreadable_encoding")
	try:
		dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
	except csv.Error:
		dialect = csv.excel
	return list(csv.reader(io.StringIO(text), dialect))


def _xlsx_rows(content: bytes) -> list[list]:
	from openpyxl import load_workbook

	workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	sheet = workbook.worksheets[0]
	return [["" if cell is None else cell for cell in row] for row in sheet.iter_rows(values_only=True)]


def to_number(value) -> Decimal | None:
	"""A number written the way Iranian programs write them: 1,250,000 or ۱٬۲۵۰٬۰۰۰ or (500) for minus.
	Empty is None; anything else that is not a number raises ValueError."""
	if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
		return Decimal(str(value))
	text = clean_text(value)
	if not text:
		return None
	negative = text.startswith("(") and text.endswith(")")
	text = text.strip("()").replace("٬", "").replace(",", "").replace("٫", ".").replace(" ", "")
	if text.endswith("-"):
		negative, text = True, text[:-1]
	try:
		number = Decimal(text)
	except InvalidOperation:
		raise ValueError("not_a_number") from None
	return -number if negative else number


# --- mapping columns to fields ----------------------------------------------------------------------

# Header names as header_key() reduces them (no spaces or half-spaces), so "کد کالا" is "کدکالا".
ALIASES = {
	"item": {
		"code": ["code", "itemcode", "sku", "کد", "کدکالا", "کدکالاخدمات", "کدمحصول"],
		"name": ["name", "itemname", "title", "نام", "نامکالا", "عنوان", "نامکالاخدمت", "شرح"],
		"group": ["group", "category", "itemgroup", "گروه", "گروهکالا", "دسته", "دستهبندی"],
		"unit": ["unit", "uom", "واحد", "واحداصلی", "واحدشمارش", "واحدسنجش"],
		"price": ["price", "rate", "sellingprice", "قیمت", "قیمتفروش", "فیفروش", "نرخفروش"],
		"sstid": ["sstid", "شناسهکالا", "شناسهکالاوخدمت", "شناسهیکتا", "شناسهعمومی", "شناسهکالاخدمت"],
		"barcode": ["barcode", "بارکد", "کدبارکد"],
	},
	"party": {
		"code": ["code", "partycode", "کد", "کدشخص", "کدمشتری", "کدطرفحساب", "کدحساب"],
		"name": ["name", "customername", "fullname", "نام", "نامشخص", "نامطرفحساب", "نامنامخانوادگی", "عنوان"],
		"type": ["type", "partytype", "نوع", "نوعشخص", "نوعطرفحساب"],
		"national_id": ["nationalid", "کدملی", "شمارهملی", "شناسهملی"],
		"economic_code": ["economiccode", "کداقتصادی", "شمارهاقتصادی"],
		"phone": ["phone", "tel", "تلفن", "شمارهتلفن", "تلفنثابت"],
		"mobile": ["mobile", "cell", "موبایل", "همراه", "تلفنهمراه", "شمارهموبایل", "شمارههمراه"],
		"address": ["address", "آدرس", "نشانی"],
		"postal_code": ["postalcode", "zip", "pincode", "کدپستی"],
		"city": ["city", "شهر"],
	},
	"stock": {
		"code": ["code", "itemcode", "کد", "کدکالا"],
		"qty": ["qty", "quantity", "stock", "موجودی", "تعداد", "مقدار", "موجودیانبار"],
		"warehouse": ["warehouse", "انبار", "نامانبار"],
		"rate": ["rate", "cost", "valuationrate", "بها", "بهایواحد", "بهایتمامشده", "نرخ", "فیخرید", "قیمتخرید"],
	},
	"balance": {
		"code": ["code", "partycode", "کد", "کدشخص", "کدمشتری", "کدطرفحساب"],
		"name": ["name", "نام", "نامشخص", "نامطرفحساب"],
		"debit": ["debit", "بدهکار", "گردشبدهکار", "ماندهبدهکار"],
		"credit": ["credit", "بستانکار", "گردشبستانکار", "ماندهبستانکار"],
		"balance": ["balance", "amount", "مانده", "مبلغ", "ماندهحساب"],
		"side": ["side", "وضعیت", "ماهیت", "نوعمانده", "تشخیص"],
	},
}

REQUIRED = {
	"item": [("name",)],
	"party": [("name",)],
	"stock": [("code",), ("qty",)],
	"balance": [("code", "name"), ("balance", "debit", "credit")],
}


def auto_map(headers: list[str], entity: str, overrides: dict | None = None) -> dict:
	"""{field: header} for the headers that are recognised. `overrides` ({field: header}) wins, so a
	column the program names oddly is fixed by hand without touching the code."""
	by_key = {header_key(header): header for header in headers}
	mapping = {}
	for field, aliases in ALIASES[entity].items():
		for alias in aliases:
			header = by_key.get(header_key(alias))
			if header:
				mapping[field] = header
				break
	for field, header in (overrides or {}).items():
		if header in headers:
			mapping[field] = header
	return mapping


def missing_columns(mapping: dict, entity: str) -> list[str]:
	"""Fields that must be present but whose column was not found. A tuple is "any one of these"."""
	return [" / ".join(group) for group in REQUIRED[entity] if not any(field in mapping for field in group)]


def _cell(row: dict, mapping: dict, field: str) -> str:
	header = mapping.get(field)
	return clean_text(row.get(header)) if header else ""


# --- turning rows into records ----------------------------------------------------------------------

# A problem is (row number in the file, code, detail). describe() puts it into words.
PROBLEM_TEXT = {
	"name_missing": "The name is empty",
	"code_missing": "The code is empty",
	"duplicate_in_file": "The code {0} is used more than once in the file",
	"bad_number": "{0} is not a number",
	"negative_quantity": "The quantity cannot be negative",
	"bad_national_id": "The national ID {0} is not valid",
	"bad_economic_code": "The economic code {0} is not valid",
	"bad_postal_code": "The postal code {0} is not valid",
	"bad_sstid": "The goods ID {0} must be 13 digits",
	"unknown_party_type": "The type {0} is neither customer nor supplier",
	"no_amount": "There is no debit, credit or balance",
	"unknown_side": "{0} is neither debit nor credit",
	"unknown_party": "No person with the code or name {0}",
}


def describe(problem: tuple) -> str:
	row, code, detail = problem
	return _("Row {0}").format(row) + ": " + _(PROBLEM_TEXT[code]).format(detail)


def _row_number(index: int) -> int:
	return index + 2  # the header is row 1


def _number(row, mapping, field, problems, row_number):
	"""The number in a cell. A cell that is not a number adds a problem and gives None."""
	text = _cell(row, mapping, field)
	try:
		return to_number(text)
	except ValueError:
		problems.append((row_number, "bad_number", f"{mapping[field]}: {text}"))
		return None


def prepare_items(rows: list[dict], mapping: dict) -> tuple[list[dict], list[tuple]]:
	records, problems, seen = [], [], set()
	for index, row in enumerate(rows):
		number = _row_number(index)
		name, code = _cell(row, mapping, "name"), _cell(row, mapping, "code")
		if not name:
			problems.append((number, "name_missing", ""))
			continue
		code = code or name
		if code in seen:
			problems.append((number, "duplicate_in_file", code))
			continue
		sstid = _cell(row, mapping, "sstid")
		if sstid and not re.fullmatch(r"\d{13}", sstid):
			problems.append((number, "bad_sstid", sstid))
			continue
		count = len(problems)
		price = _number(row, mapping, "price", problems, number)
		if len(problems) > count:
			continue
		seen.add(code)
		records.append(
			{
				"row": number,
				"code": code,
				"name": name,
				"group": _cell(row, mapping, "group"),
				"unit": _cell(row, mapping, "unit"),
				"price": price,
				"sstid": sstid,
				"barcode": _cell(row, mapping, "barcode"),
			}
		)
	return records, problems


PARTY_TYPES = {
	"customer": "Customer", "مشتری": "Customer", "خریدار": "Customer",
	"supplier": "Supplier", "تامینکننده": "Supplier", "تأمینکننده": "Supplier", "فروشنده": "Supplier",
}  # fmt: skip


def prepare_parties(
	rows: list[dict], mapping: dict, default_type: str = "Customer"
) -> tuple[list[dict], list[tuple]]:
	records, problems, seen = [], [], set()
	for index, row in enumerate(rows):
		number = _row_number(index)
		name = _cell(row, mapping, "name")
		if not name:
			problems.append((number, "name_missing", ""))
			continue
		code = _cell(row, mapping, "code")
		if code and code in seen:
			problems.append((number, "duplicate_in_file", code))
			continue

		party_type = default_type
		type_text = _cell(row, mapping, "type")
		if type_text:
			party_type = PARTY_TYPES.get(header_key(type_text))
			if not party_type:
				problems.append((number, "unknown_party_type", type_text))
				continue

		national_id = _cell(row, mapping, "national_id")
		economic_code = _cell(row, mapping, "economic_code")
		postal_code = _cell(row, mapping, "postal_code")
		checks = (
			("bad_national_id", national_id, validators.is_valid_national_id),
			("bad_economic_code", economic_code, validators.is_valid_economic_code),
			("bad_postal_code", postal_code, validators.is_valid_postal_code),
		)
		failed = next(((code_, value) for code_, value, ok in checks if value and not ok(value)), None)
		if failed:
			problems.append((number, *failed))
			continue

		if code:
			seen.add(code)
		records.append(
			{
				"row": number,
				"code": code,
				"name": name,
				"type": party_type,
				"national_id": national_id,
				"economic_code": economic_code,
				"phone": _cell(row, mapping, "phone"),
				"mobile": _cell(row, mapping, "mobile"),
				"address": _cell(row, mapping, "address"),
				"postal_code": postal_code,
				"city": _cell(row, mapping, "city"),
			}
		)
	return records, problems


def prepare_stock(rows: list[dict], mapping: dict) -> tuple[list[dict], list[tuple]]:
	records, problems = [], []
	for index, row in enumerate(rows):
		number = _row_number(index)
		code = _cell(row, mapping, "code")
		if not code:
			problems.append((number, "code_missing", ""))
			continue
		count = len(problems)
		qty = _number(row, mapping, "qty", problems, number)
		rate = _number(row, mapping, "rate", problems, number)
		if len(problems) > count:
			continue
		if qty is None or qty == 0:
			continue  # nothing in stock, nothing to open
		if qty < 0:
			problems.append((number, "negative_quantity", ""))
			continue
		records.append(
			{
				"row": number,
				"code": code,
				"qty": qty,
				"rate": rate or Decimal(0),
				"warehouse": _cell(row, mapping, "warehouse"),
			}
		)
	return records, problems


SIDES = {"بدهکار": 1, "بد": 1, "debit": 1, "dr": 1, "بستانکار": -1, "بس": -1, "credit": -1, "cr": -1}


def prepare_balances(rows: list[dict], mapping: dict) -> tuple[list[dict], list[tuple]]:
	"""Each person's opening balance as one signed number: debit minus credit. The amount may come as a
	debit and a credit column, or as one balance column (with a side column when it carries no sign)."""
	records, problems = [], []
	for index, row in enumerate(rows):
		number = _row_number(index)
		code, name = _cell(row, mapping, "code"), _cell(row, mapping, "name")
		if not (code or name):
			problems.append((number, "code_missing", ""))
			continue
		count = len(problems)
		debit = _number(row, mapping, "debit", problems, number)
		credit = _number(row, mapping, "credit", problems, number)
		balance = _number(row, mapping, "balance", problems, number)
		if len(problems) > count:
			continue

		if debit is None and credit is None and balance is None:
			problems.append((number, "no_amount", ""))
			continue
		if debit is not None or credit is not None:
			net = (debit or Decimal(0)) - (credit or Decimal(0))
		else:
			net = balance
			side_text = _cell(row, mapping, "side")
			if side_text:
				sign = SIDES.get(header_key(side_text))
				if not sign:
					problems.append((number, "unknown_side", side_text))
					continue
				net = abs(balance) * sign
		if net != 0:
			records.append({"row": number, "code": code, "name": name, "net": net})
	return records, problems


PREPARE = {
	"item": prepare_items,
	"party": prepare_parties,
	"stock": prepare_stock,
	"balance": prepare_balances,
}


def preview(entity: str, content: bytes, filename: str, overrides: dict | None = None, **options) -> dict:
	"""What importing this file would do, without writing anything."""
	headers, rows = read_table(content, filename)
	mapping = auto_map(headers, entity, overrides)
	missing = missing_columns(mapping, entity)
	if missing:
		return {"headers": headers, "mapping": mapping, "missing": missing, "records": [], "problems": []}
	records, problems = PREPARE[entity](rows, mapping, **options)
	return {"headers": headers, "mapping": mapping, "missing": [], "records": records, "problems": problems}


# --- writing into ERPNext ---------------------------------------------------------------------------


class ImportResult(dict):
	"""created / skipped (already there) / failed, each a list of (row, detail)."""

	def __init__(self):
		super().__init__(created=[], skipped=[], failed=[])


def _each_in_savepoint(records, result, create):
	"""Run create(record) for each record; one that fails is rolled back alone and reported, the rest go on."""
	for record in records:
		frappe.db.savepoint("migration_record")
		try:
			created = create(record)
		except Exception as error:
			frappe.db.rollback(save_point="migration_record")
			result["failed"].append((record["row"], str(error)))
		else:
			result["created" if created else "skipped"].append((record["row"], record.get("name") or record["code"]))
	return result


def import_items(
	records: list[dict], default_group: str = "All Item Groups", default_unit: str = "Nos"
) -> ImportResult:
	def create(record):
		if frappe.db.exists("Item", record["code"]):
			return False
		group = record["group"] or default_group
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": group, "parent_item_group": default_group}
			).insert(ignore_permissions=True)
		unit = record["unit"] or default_unit
		if not frappe.db.exists("UOM", unit):
			frappe.get_doc({"doctype": "UOM", "uom_name": unit}).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": record["code"],
				"item_name": record["name"],
				"item_group": group,
				"stock_uom": unit,
				"is_stock_item": 1,
				"standard_rate": float(record["price"] or 0),
			}
		)
		if record["sstid"]:
			doc.moadian_sstid = record["sstid"]
		if record["barcode"]:
			doc.append("barcodes", {"barcode": record["barcode"]})
		doc.insert(ignore_permissions=True)
		return True

	return _each_in_savepoint(records, ImportResult(), create)


def _existing_party(record) -> str | None:
	doctype = record["type"]
	for field in ("national_id", "economic_code"):
		if record[field] and (name := frappe.db.get_value(doctype, {field: record[field]})):
			return name
	return frappe.db.get_value(doctype, {f"{doctype.lower()}_name": record["name"]})


def import_parties(records: list[dict]) -> ImportResult:
	def create(record):
		if _existing_party(record):
			return False
		doctype = record["type"]
		doc = frappe.get_doc(
			{
				"doctype": doctype,
				f"{doctype.lower()}_name": record["name"],
				f"{doctype.lower()}_type": "Individual" if record["national_id"] else "Company",
				"national_id": record["national_id"],
				"economic_code": record["economic_code"],
				"mobile_no": record["mobile"] or None,
			}
		).insert(ignore_permissions=True)
		if record["address"] or record["postal_code"] or record["city"]:
			frappe.get_doc(
				{
					"doctype": "Address",
					"address_title": record["name"],
					"address_type": "Billing",
					"address_line1": record["address"] or record["city"] or record["name"],
					"city": record["city"] or "-",
					"country": "Iran",
					"pincode": record["postal_code"] or None,
					"phone": record["phone"] or None,
					"links": [{"link_doctype": doctype, "link_name": doc.name}],
				}
			).insert(ignore_permissions=True)
		return True

	return _each_in_savepoint(records, ImportResult(), create)


def _temporary_opening(company: str) -> str:
	"""The account an opening entry is balanced against until the real opening balances are known."""
	# By type, not by name: the Iran chart calls it «حساب افتتاحیه موقت», the standard chart "Temporary Opening".
	account = frappe.db.get_value("Account", {"company": company, "account_type": "Temporary", "is_group": 0})
	if not account:
		frappe.throw(_("Company {0} has no Temporary Opening account").format(company))
	return account


def import_opening_stock(
	records: list[dict], company: str, default_warehouse: str, posting_date: str
) -> ImportResult:
	"""One submitted Stock Reconciliation (Opening Stock) with every valid row. A row whose item or
	warehouse is not in ERPNext fails alone; the others still go in."""
	result = ImportResult()
	rows = []
	for record in records:
		warehouse = record["warehouse"] or default_warehouse
		if not frappe.db.exists("Item", record["code"]):
			result["failed"].append((record["row"], _("Item {0} does not exist").format(record["code"])))
		elif not frappe.db.exists("Warehouse", warehouse):
			result["failed"].append((record["row"], _("Warehouse {0} does not exist").format(warehouse)))
		else:
			rows.append(
				{
					"item_code": record["code"],
					"warehouse": warehouse,
					"qty": float(record["qty"]),
					"valuation_rate": float(record["rate"]),
				}
			)
			result["created"].append((record["row"], record["code"]))
	if rows:
		doc = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"purpose": "Opening Stock",
				"company": company,
				"posting_date": posting_date,
				"set_posting_time": 1,
				"expense_account": _temporary_opening(company),
				"items": rows,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
	return result


def _find_party(record) -> tuple[str, str] | None:
	for doctype in ("Customer", "Supplier"):
		for value in (record["code"], record["name"]):
			if not value:
				continue
			if frappe.db.exists(doctype, value):
				return doctype, value
			if name := frappe.db.get_value(doctype, {f"{doctype.lower()}_name": value}):
				return doctype, name
	return None


def import_opening_balances(records: list[dict], company: str, posting_date: str) -> ImportResult:
	"""One submitted opening Journal Entry: a line per person (receivable for a customer, payable for a
	supplier) and one balancing line against Temporary Opening. The people must already exist."""
	result = ImportResult()
	accounts = frappe.db.get_value(
		"Company", company, ["default_receivable_account", "default_payable_account"], as_dict=True
	)
	rows, total = [], Decimal(0)
	for record in records:
		party = _find_party(record)
		if not party:
			problem = (record["row"], "unknown_party", record["code"] or record["name"])
			result["failed"].append((record["row"], describe(problem)))
			continue
		party_type, party_name = party
		account = accounts.default_receivable_account if party_type == "Customer" else accounts.default_payable_account
		rows.append(
			{
				"account": account,
				"party_type": party_type,
				"party": party_name,
				"debit_in_account_currency": float(max(record["net"], 0)),
				"credit_in_account_currency": float(max(-record["net"], 0)),
			}
		)
		total += record["net"]
		result["created"].append((record["row"], party_name))
	if rows:
		rows.append(
			{
				"account": _temporary_opening(company),
				"debit_in_account_currency": float(max(-total, 0)),
				"credit_in_account_currency": float(max(total, 0)),
			}
		)
		doc = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Opening Entry",
				"is_opening": "Yes",
				"company": company,
				"posting_date": posting_date,
				"accounts": rows,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
	return result
