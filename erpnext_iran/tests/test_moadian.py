import datetime
import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import moadian

SELLER = {"economic_code": "411111111111", "memory_id": "A1B2C3"}
BUYER = {"economic_code": "", "national_id": "۰۴۹۹۳۷۰۸۹۹", "legal_id": ""}
ITEMS = {"SERVICE": "2720000114257"}
UNITS = {"Nos": "1627"}


def invoice(**overrides):
	data = {
		"name": "ACC-SINV-2025-00001",
		"currency": "IRR",
		"posting_date": datetime.date(2025, 3, 21),
		"posting_time": datetime.timedelta(hours=10, minutes=30),
		"taxes": [frappe._dict(rate=10)],
		"items": [
			frappe._dict(item_code="SERVICE", item_name="Consulting", uom="Nos", qty=3, rate=1500000)
		],
	}
	data.update(overrides)
	return frappe._dict(data)


class TestMoadianPayload(unittest.TestCase):
	def test_amounts_and_vat_of_a_simple_invoice(self):
		payload = moadian.build_payload(invoice(), SELLER, BUYER, ITEMS, UNITS)

		self.assertEqual(payload["body"][0]["prdis"], 4500000)
		self.assertEqual(payload["body"][0]["vam"], 450000)
		self.assertEqual(payload["body"][0]["tsstam"], 4950000)
		self.assertEqual(payload["header"]["tvam"], 450000)
		self.assertEqual(payload["header"]["tbill"], 4950000)
		self.assertEqual(payload["body"][0]["sstid"], "2720000114257")
		self.assertEqual(payload["body"][0]["mu"], "1627")

	def test_a_discount_is_taken_before_vat(self):
		doc = invoice(
			items=[frappe._dict(item_code="SERVICE", uom="Nos", qty=2, rate=1000000, discount_amount=100000)]
		)
		payload = moadian.build_payload(doc, SELLER, BUYER, ITEMS, UNITS)

		self.assertEqual(payload["header"]["tprdis"], 2000000)
		self.assertEqual(payload["header"]["tdis"], 200000)
		self.assertEqual(payload["header"]["tadis"], 1800000)
		self.assertEqual(payload["header"]["tvam"], 180000)

	def test_toman_is_sent_as_rial(self):
		payload = moadian.build_payload(invoice(currency="IRT"), SELLER, BUYER, ITEMS, UNITS)

		self.assertEqual(payload["body"][0]["fee"], 15000000)
		self.assertEqual(payload["header"]["tbill"], 49500000)

	def test_identifiers_are_sent_with_latin_digits(self):
		header = moadian.build_payload(invoice(), SELLER, BUYER, ITEMS, UNITS)["header"]

		self.assertEqual(header["bid"], "0499370899")
		self.assertEqual(header["tins"], "411111111111")

	def test_the_time_is_unix_milliseconds_in_tehran_time(self):
		# 2025-03-21 10:30 in Tehran (UTC+3:30, no summer time any more) is 07:00 UTC
		expected = int(datetime.datetime(2025, 3, 21, 7, 0, tzinfo=datetime.timezone.utc).timestamp() * 1000)

		self.assertEqual(moadian.to_millis(datetime.date(2025, 3, 21), datetime.timedelta(hours=10, minutes=30)), expected)
		self.assertEqual(moadian.to_millis("2025-03-21", "10:30:00"), expected)

	def test_the_payload_says_it_is_unverified(self):
		self.assertTrue(moadian.build_payload(invoice(), SELLER, BUYER, ITEMS, UNITS)["unverified"])

	def test_missing_data_is_listed_in_plain_words(self):
		with patch.object(moadian, "_", side_effect=lambda text: text):
			missing = moadian.missing_data(invoice(), {}, {}, {}, {})

		self.assertEqual(len(missing), 5)
		self.assertEqual(moadian.missing_data(invoice(), SELLER, BUYER, ITEMS, UNITS), [])

	def test_no_tax_row_means_zero_vat(self):
		payload = moadian.build_payload(invoice(taxes=[]), SELLER, BUYER, ITEMS, UNITS)

		self.assertEqual(payload["header"]["tvam"], 0)
		self.assertEqual(payload["header"]["tbill"], 4500000)


class TestMoadianPatterns(unittest.TestCase):
	def test_plain_sale_carries_every_mandatory_field_of_pattern_one(self):
		payload = moadian.build_payload(invoice(), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual(moadian.pattern_gaps(payload), [])

	def test_gold_pattern_asks_for_wage_profit_and_commission_on_top_of_a_plain_sale(self):
		plain = moadian.pattern_fields(1, 1)
		gold = moadian.pattern_fields(1, 3)
		for code in ("bros", "consfee", "spro", "tcpbs"):
			self.assertEqual((plain.get(code), gold[code]), (None, "mandatory"))

	def test_a_pattern_the_invoice_type_does_not_have_is_refused_with_its_number(self):
		payload = moadian.build_payload(
			invoice(moadian_invoice_type="2", moadian_pattern="8"), SELLER, BUYER, ITEMS, UNITS
		)
		with self.assertRaisesRegex(ValueError, "Pattern 8 is not valid for invoice type 2"):
			moadian.pattern_gaps(payload)


def pattern_invoice(pattern, **extra):
	row = frappe._dict(item_code="SERVICE", item_name="Ring", uom="Nos", qty=2, rate=1000000)
	row.update(extra.pop("row", {}))
	return invoice(moadian_pattern=str(pattern), items=[row], **extra)


class TestMoadianEveryPattern(unittest.TestCase):
	def test_export_sends_rial_and_currency_values_and_leaves_out_the_totals_it_ignores(self):
		row = {"moadian_ssrv": 500, "moadian_sscv": 10, "moadian_cut": "USD", "moadian_exr": 50}
		payload = moadian.build_payload(pattern_invoice(7, row=row), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual((payload["header"]["torv"], payload["header"]["tocv"]), (500, 10))
		self.assertNotIn("prdis", payload["body"][0])
		self.assertNotIn("tprdis", payload["header"])
		self.assertEqual(moadian.pattern_gaps(payload), [])

	def test_gold_reports_the_wage_profit_and_commission_it_still_lacks(self):
		payload = moadian.build_payload(pattern_invoice(3), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual(sorted(moadian.pattern_gaps(payload)), ["bros", "consfee", "spro", "tcpbs"])

	def test_gold_with_wage_profit_and_commission_has_no_gap(self):
		row = {"moadian_consfee": 10, "moadian_spro": 20, "moadian_bros": 5, "moadian_tcpbs": 35}
		payload = moadian.build_payload(pattern_invoice(3, row=row), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual(moadian.pattern_gaps(payload), [])

	def test_air_ticket_needs_the_flight_type_and_sends_it_when_given(self):
		self.assertIn("ft", moadian.pattern_gaps(moadian.build_payload(pattern_invoice(6), SELLER, BUYER, ITEMS, UNITS)))
		payload = moadian.build_payload(pattern_invoice(6, moadian_ft=1), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual(payload["header"]["ft"], 1)
		self.assertEqual(moadian.pattern_gaps(payload), [])

	def test_a_field_the_pattern_ignores_is_not_sent_even_if_filled(self):
		payload = moadian.build_payload(pattern_invoice(1, moadian_ft=1), SELLER, BUYER, ITEMS, UNITS)
		self.assertNotIn("ft", payload["header"])

	def test_each_item_uses_its_own_vat_rate_when_it_has_one(self):
		rows = [
			frappe._dict(item_code="SERVICE", item_name="A", uom="Nos", qty=1, rate=1000, item_tax_rate='{"VAT - X": 9}'),
			frappe._dict(item_code="SERVICE", item_name="B", uom="Nos", qty=1, rate=1000, item_tax_rate='{"VAT - X": 0}'),
			frappe._dict(item_code="SERVICE", item_name="C", uom="Nos", qty=1, rate=1000),
		]
		payload = moadian.build_payload(invoice(items=rows), SELLER, BUYER, ITEMS, UNITS)
		self.assertEqual([line["vam"] for line in payload["body"]], [90, 0, 100])
		self.assertEqual(payload["header"]["tvam"], 190)

	def test_sales_return_is_subject_four_with_positive_amounts_and_points_at_the_original(self):
		rows = [frappe._dict(item_code="SERVICE", item_name="A", uom="Nos", qty=-2, rate=1000)]
		payload = moadian.build_payload(
			invoice(items=rows, is_return=1, moadian_reference_tax_id="A1121604C220002F095011"),
			SELLER, BUYER, ITEMS, UNITS,
		)
		self.assertEqual((payload["header"]["ins"], payload["header"]["irtaxid"]), (4, "A1121604C220002F095011"))
		self.assertEqual(payload["body"][0]["am"], 2)


class TestMoadianOptionCodes(unittest.TestCase):
	def test_the_number_of_a_select_option_is_what_goes_to_moadian(self):
		self.assertEqual(moadian.code_of("3 - Gold, jewellery and platinum"), 3)
		self.assertEqual(moadian.code_of("11 - Securities (bourse)"), 11)
		self.assertEqual(moadian.code_of("2"), 2)
		self.assertEqual(moadian.code_of(None, 5), 5)

	def test_a_payload_reads_the_pattern_from_the_words_the_user_picked(self):
		payload = moadian.build_payload(
			invoice(moadian_pattern="6 - Air ticket", moadian_settlement_method="2 - Credit"), SELLER, BUYER, ITEMS, UNITS
		)
		self.assertEqual((payload["header"]["inp"], payload["header"]["setm"]), (6, 2))
