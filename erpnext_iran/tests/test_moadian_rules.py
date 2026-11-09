import unittest

import frappe

from erpnext_iran import moadian, moadian_rules
from erpnext_iran.tests.test_moadian import BUYER, ITEMS, SELLER, UNITS, invoice, pattern_invoice

NOW = 1_742_504_400_000 + 10**9


def problems(**overrides):
	buyer = overrides.pop("buyer", BUYER)
	seller = overrides.pop("seller", SELLER)
	payload = moadian.build_payload(invoice(**overrides), seller, buyer, ITEMS, UNITS)
	return moadian_rules.data_problems(payload, now_millis=NOW)


class TestMoadianRules(unittest.TestCase):
	def test_a_valid_company_invoice_with_a_legal_buyer_has_no_problem(self):
		buyer = {"national_id": "", "legal_id": "10100302746", "economic_code": "10100302746"}
		self.assertEqual(problems(moadian_buyer_type="2 - Company", buyer=buyer), [])

	def test_the_seller_economic_code_must_have_eleven_or_fourteen_digits(self):
		buyer = {"national_id": "", "legal_id": "10100302746", "economic_code": "10100302746"}
		found = problems(seller={"economic_code": "411111111111"}, moadian_buyer_type="2 - Company", buyer=buyer)
		self.assertEqual(found, ["The economic code of the company (Tax ID) must be 11 or 14 digits"])

	def test_a_legal_buyer_without_an_economic_code_is_reported(self):
		buyer = {"national_id": "", "legal_id": "10100302746", "economic_code": ""}
		self.assertIn("A legal buyer needs an economic code", problems(moadian_buyer_type="2 - Company", buyer=buyer))

	def test_a_real_buyer_needs_a_postal_code_besides_the_national_number(self):
		buyer = {"national_id": "0499370899", "legal_id": "", "economic_code": ""}
		found = problems(moadian_buyer_type="1 - Individual", buyer=buyer)
		self.assertEqual(found, ["A real or foreign buyer needs a postal code (Address of the customer)"])
		self.assertEqual(problems(moadian_buyer_type="1 - Individual", buyer=buyer, moadian_bpc="1234567890"), [])

	def test_a_buyer_id_of_the_wrong_length_for_its_type_is_reported(self):
		buyer = {"national_id": "049937089", "legal_id": "", "economic_code": ""}
		found = problems(moadian_buyer_type="1 - Individual", buyer=buyer, moadian_bpc="1234567890")
		self.assertEqual(found, ["The buyer ID must be 10 digits for this type of buyer"])

	def test_a_type_two_invoice_needs_no_buyer(self):
		self.assertEqual(problems(moadian_invoice_type="2 - Type 2 (buyer optional)", buyer={}), [])

	def test_an_invoice_dated_in_the_future_is_reported(self):
		found = moadian_rules.data_problems(
			moadian.build_payload(invoice(moadian_invoice_type="2"), SELLER, {}, ITEMS, UNITS), now_millis=1
		)
		self.assertIn("The invoice date and time are in the future", found)

	def test_an_air_ticket_row_with_two_units_and_a_zero_price_invoice_are_reported(self):
		payload = moadian.build_payload(pattern_invoice(6, moadian_ft="1 - Domestic flight"), SELLER, {}, ITEMS, UNITS)
		self.assertIn("Row 1: this pattern allows a quantity of 1 only", moadian_rules.data_problems(payload, now_millis=NOW))
		free = moadian.build_payload(invoice(items=[frappe._dict(item_code="SERVICE", item_name="A", uom="Nos", qty=1, rate=0)]), SELLER, BUYER, ITEMS, UNITS)
		self.assertIn("The invoice total must be above zero", moadian_rules.data_problems(free, now_millis=NOW))

	def test_a_goods_id_that_is_not_thirteen_digits_is_reported(self):
		payload = moadian.build_payload(invoice(), SELLER, BUYER, {"SERVICE": "123"}, UNITS)
		self.assertIn("Row 1: the goods or service ID must be 13 digits", moadian_rules.data_problems(payload, now_millis=NOW))

	def test_an_invoice_older_than_the_late_window_carries_its_registration_time(self):
		old = invoice(moadian_late_after_hours=48, moadian_now_millis=1_742_504_400_000 + 5 * 86_400_000)
		header = moadian.build_payload(old, SELLER, BUYER, ITEMS, UNITS)["header"]
		self.assertEqual((header["insr"], header["indati2m"]), (1, 1_742_504_400_000 + 5 * 86_400_000))
		fresh = invoice(moadian_late_after_hours=48, moadian_now_millis=1_742_504_400_000 + 86_400_000)
		self.assertNotIn("insr", moadian.build_payload(fresh, SELLER, BUYER, ITEMS, UNITS)["header"])
