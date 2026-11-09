import io
import unittest
from decimal import Decimal
from unittest.mock import patch

from erpnext_iran import migration


def csv_bytes(text: str, encoding="utf-8") -> bytes:
	return text.encode(encoding)


class TestReadingTheFile(unittest.TestCase):
	def test_a_persian_csv_in_windows_1256_is_read(self):
		# Windows-1256 has no Persian ی and no Persian digits: real files carry Arabic ي and 0-9.
		content = csv_bytes("کد کالا,نام کالا\n101,رژ لب\n", "cp1256")

		headers, rows = migration.read_table(content, "kala.csv")

		self.assertEqual(headers, ["کد کالا", "نام کالا"])
		self.assertEqual(rows, [{"کد کالا": "101", "نام کالا": "رژ لب"}])

	def test_semicolon_separated_csv_with_a_bom_is_read(self):
		headers, rows = migration.read_table(csv_bytes("﻿code;name\n1;Lipstick\n"), "a.csv")

		self.assertEqual(headers, ["code", "name"])
		self.assertEqual(rows[0]["name"], "Lipstick")

	def test_arabic_letters_become_persian_and_empty_rows_are_dropped(self):
		_, rows = migration.read_table(csv_bytes("name\nعلي كريمي\n,\n"), "a.csv")

		self.assertEqual(rows, [{"name": "علی کریمی"}])

	def test_xlsx_is_read(self):
		from openpyxl import Workbook

		book = Workbook()
		book.active.append(["code", "qty"])
		book.active.append(["A1", 5])
		stream = io.BytesIO()
		book.save(stream)

		headers, rows = migration.read_table(stream.getvalue(), "stock.xlsx")

		self.assertEqual(headers, ["code", "qty"])
		self.assertEqual(rows, [{"code": "A1", "qty": "5"}])

	def test_an_unknown_file_type_and_an_empty_file_are_refused(self):
		with self.assertRaisesRegex(ValueError, "unsupported_file"):
			migration.read_table(b"x", "a.pdf")
		with self.assertRaisesRegex(ValueError, "empty_file"):
			migration.read_table(b"\n\n", "a.csv")


class TestNumbers(unittest.TestCase):
	def test_the_ways_a_program_writes_a_number(self):
		to_number = migration.to_number
		self.assertEqual(to_number("1,250,000"), Decimal("1250000"))
		self.assertEqual(to_number("۱٬۲۵۰٬۰۰۰"), Decimal("1250000"))
		self.assertEqual(to_number("(500)"), Decimal("-500"))
		self.assertEqual(to_number("500-"), Decimal("-500"))
		self.assertEqual(to_number("۲٫۵"), Decimal("2.5"))
		self.assertEqual(to_number(7), Decimal("7"))
		self.assertIsNone(to_number(""))

	def test_text_is_not_a_number(self):
		with self.assertRaises(ValueError):
			migration.to_number("ده")


class TestMapping(unittest.TestCase):
	def test_persian_headers_are_recognised_whatever_the_spacing(self):
		headers = ["کد کالا", "نام‌کالا", "گروه کالا", "واحد", "قیمت فروش", "شناسه کالا و خدمت"]

		mapping = migration.auto_map(headers, "item")

		self.assertEqual(
			mapping,
			{
				"code": "کد کالا",
				"name": "نام‌کالا",
				"group": "گروه کالا",
				"unit": "واحد",
				"price": "قیمت فروش",
				"sstid": "شناسه کالا و خدمت",
			},
		)

	def test_a_mapping_given_by_hand_wins(self):
		mapping = migration.auto_map(["Title", "Cost"], "item", {"name": "Title", "price": "Cost"})

		self.assertEqual(mapping, {"name": "Title", "price": "Cost"})

	def test_a_hand_mapping_to_a_column_that_does_not_exist_is_ignored(self):
		self.assertEqual(migration.auto_map(["a"], "item", {"name": "zzz"}), {})

	def test_missing_required_columns_are_named(self):
		self.assertEqual(migration.missing_columns({}, "stock"), ["code", "qty"])
		self.assertEqual(migration.missing_columns({"code": "c", "debit": "d"}, "balance"), [])
		self.assertEqual(migration.missing_columns({"name": "n"}, "balance"), ["balance / debit / credit"])


class TestItems(unittest.TestCase):
	MAPPING = {"code": "code", "name": "name", "price": "price", "sstid": "sstid"}

	def prepare(self, *rows):
		return migration.prepare_items(list(rows), self.MAPPING)

	def test_a_good_row_becomes_a_record(self):
		records, problems = self.prepare(
			{"code": "A1", "name": "Lipstick", "price": "1,250,000", "sstid": "2710000000000"}
		)

		self.assertEqual(problems, [])
		self.assertEqual(records[0]["price"], Decimal("1250000"))
		self.assertEqual(records[0]["row"], 2)

	def test_without_a_code_the_name_is_the_code(self):
		records, _ = self.prepare({"name": "Lipstick"})

		self.assertEqual(records[0]["code"], "Lipstick")

	def test_bad_rows_are_reported_with_their_row_number_and_the_rest_go_on(self):
		records, problems = self.prepare(
			{"code": "A1", "name": "One"},
			{"code": "A2", "name": ""},
			{"code": "A1", "name": "Again"},
			{"code": "A3", "name": "Three", "sstid": "123"},
			{"code": "A4", "name": "Four", "price": "cheap"},
			{"code": "A5", "name": "Five"},
		)

		self.assertEqual([r["code"] for r in records], ["A1", "A5"])
		self.assertEqual(
			[(row, code) for row, code, _ in problems],
			[(3, "name_missing"), (4, "duplicate_in_file"), (5, "bad_sstid"), (6, "bad_number")],
		)

	def test_an_item_without_an_official_id_is_still_imported(self):
		# It is blocked later, when an invoice for it would be sent; the migration must not lose it.
		records, problems = self.prepare({"code": "A1", "name": "One"})

		self.assertEqual((len(records), problems), (1, []))
		self.assertEqual(records[0]["sstid"], "")


class TestParties(unittest.TestCase):
	MAPPING = {"code": "code", "name": "name", "type": "type", "national_id": "nid", "economic_code": "eco"}

	def prepare(self, *rows):
		return migration.prepare_parties(list(rows), self.MAPPING)

	def test_the_type_is_read_in_persian_and_defaults_to_customer(self):
		records, problems = self.prepare(
			{"name": "A", "type": "تامین کننده"}, {"name": "B"}, {"name": "C", "type": "مشتری"}
		)

		self.assertEqual(problems, [])
		self.assertEqual([r["type"] for r in records], ["Supplier", "Customer", "Customer"])

	def test_an_unknown_type_is_a_problem(self):
		_, problems = self.prepare({"name": "A", "type": "همکار"})

		self.assertEqual(problems[0][1], "unknown_party_type")

	def test_a_national_id_is_checked_and_persian_digits_are_accepted(self):
		records, problems = self.prepare(
			{"name": "A", "nid": "۰۴۹۹۳۷۰۸۹۹"}, {"name": "B", "nid": "0499370898"}
		)

		self.assertEqual(records[0]["national_id"], "0499370899")
		self.assertEqual(problems, [(3, "bad_national_id", "0499370898")])

	def test_a_wrong_economic_code_is_a_problem(self):
		_, problems = self.prepare({"name": "A", "eco": "123"})

		self.assertEqual(problems, [(2, "bad_economic_code", "123")])


class TestStock(unittest.TestCase):
	MAPPING = {"code": "code", "qty": "qty", "rate": "rate", "warehouse": "wh"}

	def test_zero_stock_is_left_out_and_negative_stock_is_a_problem(self):
		records, problems = migration.prepare_stock(
			[
				{"code": "A", "qty": "3", "rate": "100"},
				{"code": "B", "qty": "0"},
				{"code": "C", "qty": "-2"},
				{"code": "", "qty": "1"},
			],
			self.MAPPING,
		)

		self.assertEqual([(r["code"], r["qty"], r["rate"]) for r in records], [("A", Decimal(3), Decimal(100))])
		self.assertEqual(
			[(row, code) for row, code, _ in problems], [(4, "negative_quantity"), (5, "code_missing")]
		)


class TestBalances(unittest.TestCase):
	def test_debit_and_credit_columns_give_one_signed_number(self):
		mapping = {"name": "name", "debit": "d", "credit": "c"}

		records, problems = migration.prepare_balances(
			[
				{"name": "A", "d": "1,000", "c": ""},
				{"name": "B", "d": "", "c": "400"},
				{"name": "C", "d": "50", "c": "50"},
				{"name": "D", "d": "", "c": ""},
			],
			mapping,
		)

		self.assertEqual([(r["name"], r["net"]) for r in records], [("A", Decimal(1000)), ("B", Decimal(-400))])
		self.assertEqual(problems, [(5, "no_amount", "")])

	def test_one_balance_column_with_a_side_column(self):
		mapping = {"code": "code", "balance": "bal", "side": "side"}

		records, problems = migration.prepare_balances(
			[
				{"code": "1", "bal": "500", "side": "بدهکار"},
				{"code": "2", "bal": "500", "side": "بستانکار"},
				{"code": "3", "bal": "500", "side": "؟"},
			],
			mapping,
		)

		self.assertEqual([r["net"] for r in records], [Decimal(500), Decimal(-500)])
		self.assertEqual(problems[0][:2], (4, "unknown_side"))

	def test_a_signed_balance_without_a_side_keeps_its_sign(self):
		records, _ = migration.prepare_balances(
			[{"name": "A", "bal": "(700)"}], {"name": "name", "balance": "bal"}
		)

		self.assertEqual(records[0]["net"], Decimal(-700))


class TestPreview(unittest.TestCase):
	def test_preview_reports_the_columns_it_could_not_find(self):
		result = migration.preview("stock", csv_bytes("a,b\n1,2\n"), "a.csv")

		self.assertEqual(result["missing"], ["code", "qty"])
		self.assertEqual(result["records"], [])

	def test_preview_of_a_whole_file(self):
		content = csv_bytes('کد کالا,نام کالا,قيمت فروش\n1,رژ,"1,000"\n2,,5\n', "cp1256")

		result = migration.preview("item", content, "kala.csv")

		self.assertEqual([r["code"] for r in result["records"]], ["1"])
		self.assertEqual(result["problems"], [(3, "name_missing", "")])

	def test_preview_passes_the_default_party_type(self):
		result = migration.preview("party", csv_bytes("name\nA\n"), "a.csv", default_type="Supplier")

		self.assertEqual(result["records"][0]["type"], "Supplier")


class TestDescribe(unittest.TestCase):
	def test_a_problem_is_put_into_words(self):
		with patch.object(migration, "_", side_effect=lambda text: text):
			self.assertEqual(
				migration.describe((3, "bad_sstid", "12")), "Row 3: The goods ID 12 must be 13 digits"
			)
