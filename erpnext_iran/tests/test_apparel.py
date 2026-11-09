import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import apparel
from erpnext_iran.erpnext_iran.report.sell_through import sell_through
from erpnext_iran.erpnext_iran.report.stock_matrix import stock_matrix
from erpnext_iran.scale import ean13_check_digit


class TestChoices(unittest.TestCase):
	ROWS = [frappe._dict(attribute_value="Small", abbr="S"), frappe._dict(attribute_value="Large", abbr="L"), frappe._dict(attribute_value="سیاه", abbr="SYH")]

	def resolve(self, values):
		with patch.object(apparel.frappe, "get_all", return_value=self.ROWS):
			return apparel.clean_choices(values, "Size")

	def test_a_value_may_be_named_by_its_name_or_its_short_code(self):
		self.assertEqual(self.resolve(["Small", "l", "SYH"]), ["Small", "Large", "سیاه"])

	def test_duplicates_collapse_and_blanks_are_ignored(self):
		self.assertEqual(self.resolve(["S", "Small", " ", "s"]), ["Small"])

	def test_an_unknown_value_is_refused_by_name(self):
		with self.assertRaises(frappe.ValidationError) as error:
			self.resolve(["Small", "XXXL"])
		self.assertIn("XXXL", str(error.exception))

	def test_nothing_chosen_is_refused(self):
		for empty in ([], None, ["", " "]):
			with self.assertRaises(frappe.ValidationError):
				self.resolve(empty)

	def test_json_from_the_browser_is_accepted(self):
		self.assertEqual(self.resolve('["S", "L"]'), ["Small", "Large"])


class TestStyleCode(unittest.TestCase):
	def test_what_a_code_may_look_like(self):
		for good in ("SH", "SHIRT-101", "a1-b2", "X" * 30):
			self.assertTrue(apparel.STYLE_CODE.match(good), good)
		for bad in ("", "A", "has space", "slash/ed", "نام", "X" * 31, "semi;colon", "a_b"):
			self.assertFalse(apparel.STYLE_CODE.match(bad), bad)


class TestBarcodes(unittest.TestCase):
	def codes(self, count, last=None, prefix="29"):
		with patch("iran_base.settings.get_setting", return_value=prefix), patch.object(apparel.frappe.db, "sql", return_value=[[last]]):
			return apparel.next_barcodes(count)

	def test_codes_run_on_from_the_last_one_and_have_valid_check_digits(self):
		codes = self.codes(3, last=117)
		self.assertEqual([c[2:12] for c in codes], ["0000000118", "0000000119", "0000000120"])
		for code in codes:
			self.assertEqual(len(code), 13)
			self.assertEqual(code[12], ean13_check_digit(code[:12]))
			self.assertTrue(code.startswith("29"))

	def test_the_first_code_starts_at_one(self):
		self.assertEqual(self.codes(1, last=None)[0][:12], "290000000001")

	def test_a_bad_prefix_is_refused(self):
		for bad in ("ab", "1234567", ""):
			if bad == "":
				continue  # empty falls back to 29
			with self.assertRaises(frappe.ValidationError):
				self.codes(1, prefix=bad)

	def test_the_numbers_can_run_out(self):
		with self.assertRaises(frappe.ValidationError):
			self.codes(1, last=10**10 - 1, prefix="29")  # ten digits of room, all used

	def test_the_scale_prefix_does_not_clash_with_the_default(self):
		from erpnext_iran.scale import DEFAULTS

		self.assertNotEqual(DEFAULTS["prefix"], "29")
		self.assertFalse(DEFAULTS["prefix"] and "29".startswith(DEFAULTS["prefix"]) and len(DEFAULTS["prefix"]) > 1)


class TestSeason(unittest.TestCase):
	def test_a_variant_takes_the_season_of_its_template(self):
		doc = frappe._dict(variant_of="T", season="")
		with patch.object(apparel.frappe.db, "get_value", return_value="تابستان"):
			apparel.inherit_season(doc)
		self.assertEqual(doc.season, "تابستان")

	def test_a_season_set_on_the_variant_is_kept_and_a_plain_item_is_untouched(self):
		own = frappe._dict(variant_of="T", season="زمستان")
		plain = frappe._dict(variant_of=None, season="")
		with patch.object(apparel.frappe.db, "get_value", return_value="تابستان"):
			apparel.inherit_season(own)
			apparel.inherit_season(plain)
		self.assertEqual((own.season, plain.season), ("زمستان", ""))

	def test_the_season_list_matches_the_field_options(self):
		options = [o for o in frappe.get_meta("Item").get_field("season").options.split("\n") if o]
		self.assertEqual(options, list(apparel.SEASONS))


class TestReports(unittest.TestCase):
	def test_sell_through_percent(self):
		self.assertAlmostEqual(sell_through.percent(9, 26), 9 / 35 * 100)
		self.assertEqual(sell_through.percent(0, 0), 0)
		self.assertEqual(sell_through.percent(10, 0), 100)
		self.assertEqual(sell_through.percent(0, 40), 0)
		self.assertEqual(sell_through.percent(-3, 5), 0)  # returns beat sales

	def test_a_company_without_warehouses_gives_an_empty_matrix_not_an_error(self):
		with patch.object(stock_matrix.frappe, "get_all", return_value=[]):
			self.assertEqual(stock_matrix.get_matrix(frappe._dict(company="Nobody")), ([], []))

	def test_the_endpoints_that_create_things_are_post_only(self):
		for function in (apparel.make_style, apparel.season_clearance):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[function], ["POST"])


class TestSeasonClearance(unittest.TestCase):
	def run_clearance(self, season="تابستان", percent=30, start="2026-01-01", end="2026-02-01", items=("T1",)):
		with patch.object(apparel.frappe, "has_permission"), patch.object(apparel.frappe, "get_all", return_value=list(items)):
			return apparel.season_clearance(season, percent, start, end)

	def test_bad_requests_are_refused_before_anything_is_made(self):
		for kwargs in ({"season": "x"}, {"percent": 0}, {"percent": -5}, {"percent": 91}, {"start": "2026-03-01", "end": "2026-02-01"}, {"items": ()}):
			with self.subTest(kwargs):
				with self.assertRaises(frappe.ValidationError):
					self.run_clearance(**kwargs)
