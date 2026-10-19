import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import validations


class FakeDoc(dict):
	def set(self, key, value):
		self[key] = value


class TestValidations(unittest.TestCase):
	def setUp(self):
		patcher = patch.object(validations.frappe, "throw", side_effect=frappe.ValidationError)
		self.throw = patcher.start()
		self.addCleanup(patcher.stop)

	def test_a_valid_national_id_passes_and_persian_digits_are_stored_as_latin(self):
		doc = FakeDoc(national_id="۰۴۹۹۳۷۰۸۹۹")

		validations.validate_party(doc)

		self.assertEqual(doc["national_id"], "0499370899")

	def test_a_wrong_national_id_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			validations.validate_party(FakeDoc(national_id="0499370898"))

	def test_empty_identifiers_are_allowed(self):
		validations.validate_party(FakeDoc())
		self.throw.assert_not_called()

	def test_postal_code_is_only_checked_for_iran(self):
		validations.validate_address(FakeDoc(country="Germany", pincode="12345"))
		self.throw.assert_not_called()

		with self.assertRaises(frappe.ValidationError):
			validations.validate_address(FakeDoc(country="Iran", pincode="12345"))
