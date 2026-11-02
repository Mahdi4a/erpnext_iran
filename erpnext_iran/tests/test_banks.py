import unittest
from unittest.mock import patch

from erpnext_iran import banks, validations


class FakeDoc(dict):
	def set(self, key, value):
		self[key] = value


class TestBanks(unittest.TestCase):
	def test_the_bank_code_is_read_from_a_sheba_in_any_spelling(self):
		for value in ("IR360120000000000000000000", "ir36 0120 0000 0000 0000 0000 00", "360120000000000000000000"):
			self.assertEqual(banks.sheba_bank_code(value), "012")

	def test_something_that_is_not_an_iranian_sheba_has_no_bank_code(self):
		for value in ("", None, "DE89370400440532013000", "IR12"):
			self.assertIsNone(banks.sheba_bank_code(value))

	def test_every_code_is_three_digits_and_used_once(self):
		self.assertTrue(all(len(code) == 3 and code.isdigit() for code in banks.BANKS))
		self.assertEqual(len(set(banks.BANKS.values())), len(banks.BANKS))

	def test_an_empty_bank_is_filled_in_from_the_sheba(self):
		doc = FakeDoc()
		with patch.object(banks, "bank_for_sheba", return_value="بانک ملت"):
			validations._match_bank(doc, "IR360120000000000000000000")
		self.assertEqual(doc["bank"], "بانک ملت")

	def test_a_bank_that_differs_is_kept_and_warned_about(self):
		doc = FakeDoc(bank="بانک ملی ایران")
		with (
			patch.object(banks, "bank_for_sheba", return_value="بانک ملت"),
			patch.object(validations.frappe, "msgprint") as msgprint,
		):
			validations._match_bank(doc, "IR360120000000000000000000")
		self.assertEqual(doc["bank"], "بانک ملی ایران")
		msgprint.assert_called_once()
