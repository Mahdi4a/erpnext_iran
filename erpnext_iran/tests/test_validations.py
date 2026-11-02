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


class TestProvince(unittest.TestCase):
	def test_the_chosen_province_becomes_the_state(self):
		doc = FakeDoc(country="Iran", iran_province="گیلان", state="")
		validations.validate_address(doc)
		self.assertEqual(doc["state"], "گیلان")

	def test_a_state_that_is_a_province_fills_the_province(self):
		doc = FakeDoc(country="Iran", state="یزد")
		validations.validate_address(doc)
		self.assertEqual(doc["iran_province"], "یزد")

	def test_another_country_is_left_alone(self):
		doc = FakeDoc(country="Germany", iran_province="گیلان", state="Bavaria")
		validations.validate_address(doc)
		self.assertEqual(doc["state"], "Bavaria")

	def test_there_are_31_provinces(self):
		from erpnext_iran.fields import PROVINCES

		self.assertEqual(len(PROVINCES), 31)
		self.assertEqual(len(set(PROVINCES)), 31)
