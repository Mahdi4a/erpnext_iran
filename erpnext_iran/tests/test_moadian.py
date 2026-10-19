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
