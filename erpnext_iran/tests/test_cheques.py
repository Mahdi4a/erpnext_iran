import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import cheques, validations

SHEBA = "IR062960000000100324200001"


class FakeDoc(dict):
	def set(self, key, value):
		self[key] = value


class TestSheba(unittest.TestCase):
	def setUp(self):
		patcher = patch.object(validations.frappe, "throw", side_effect=frappe.ValidationError)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_a_valid_sheba_passes_with_spaces_lowercase_persian_digits_or_without_ir(self):
		for value in (SHEBA, "ir06 2960 0000 0010 0324 2000 01", "062960000000100324200001", "IR۰۶۲۹۶۰۰۰۰۰۰۰۱۰۰۳۲۴۲۰۰۰۰۱"):
			self.assertTrue(validations.is_valid_sheba(value), value)

	def test_a_wrong_check_digit_or_length_is_refused(self):
		for value in ("IR062960000000100324200002", "IR0629600000001003242000", "IR06296000000010032420000X1"):
			self.assertFalse(validations.is_valid_sheba(value), value)

	def test_bank_account_saves_the_normalised_sheba(self):
		doc = FakeDoc(iban="ir06 2960 0000 0010 0324 2000 01")
		validations.validate_bank_account(doc)
		self.assertEqual(doc["iban"], SHEBA)

	def test_a_bad_iranian_sheba_blocks_the_bank_account(self):
		with self.assertRaises(frappe.ValidationError):
			validations.validate_bank_account(FakeDoc(iban="IR062960000000100324200002"))

	def test_a_foreign_iban_and_an_empty_value_are_left_to_erpnext(self):
		validations.validate_bank_account(FakeDoc(iban="DE89370400440532013000"))
		validations.validate_bank_account(FakeDoc())


ACCOUNTS = {
	"cheques_in_hand": "HAND",
	"cheques_in_collection": "COLLECTION",
	"cheques_payable": "PAYABLE",
	"bank": "BANK",
	"party": {"account": "PARTY", "party_type": "Customer", "party": "C1"},
	"endorsed_to": {"account": "SUPPLIER", "party_type": "Supplier", "party": "S1"},
}


def entry(cheque_type, step):
	return [(line["side"], line["account"]) for line in cheques.posting_lines(cheque_type, step, ACCOUNTS)]


class TestChequeFlow(unittest.TestCase):
	def setUp(self):
		patcher = patch.object(cheques.frappe, "throw", side_effect=frappe.ValidationError)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_a_received_cheque_goes_from_hand_to_collection_to_the_bank(self):
		self.assertEqual(cheques.next_status("Received", "In Hand", "deposit"), "Deposited")
		self.assertEqual(cheques.next_status("Received", "Deposited", "clear"), "Cleared")
		self.assertEqual(cheques.next_status("Received", "Deposited", "bounce"), "Bounced")

	def test_steps_that_do_not_exist_are_refused(self):
		for args in (
			("Received", "In Hand", "clear"),
			("Received", "Cleared", "deposit"),
			("Issued", "Issued", "deposit"),
			("Issued", "Issued", "endorse"),
			("Issued", "Cleared", "bounce"),
		):
			with self.assertRaises(frappe.ValidationError):
				cheques.next_status(*args)

	def test_available_actions(self):
		self.assertEqual(cheques.available_actions("Received", "In Hand"), ["deposit", "endorse"])
		self.assertEqual(cheques.available_actions("Issued", "Cleared"), [])

	def test_received_cheque_postings(self):
		self.assertEqual(entry("Received", "submit"), [("debit", "HAND"), ("credit", "PARTY")])
		self.assertEqual(entry("Received", "deposit"), [("debit", "COLLECTION"), ("credit", "HAND")])
		self.assertEqual(entry("Received", "clear"), [("debit", "BANK"), ("credit", "COLLECTION")])
		self.assertEqual(entry("Received", "bounce"), [("debit", "PARTY"), ("credit", "COLLECTION")])
		self.assertEqual(entry("Received", "endorse"), [("debit", "SUPPLIER"), ("credit", "HAND")])

	def test_issued_cheque_postings(self):
		self.assertEqual(entry("Issued", "submit"), [("debit", "PARTY"), ("credit", "PAYABLE")])
		self.assertEqual(entry("Issued", "clear"), [("debit", "PAYABLE"), ("credit", "BANK")])
		self.assertEqual(entry("Issued", "bounce"), [("debit", "PAYABLE"), ("credit", "PARTY")])

	def test_party_lines_carry_the_party_and_other_lines_do_not(self):
		lines = cheques.posting_lines("Received", "submit", ACCOUNTS)
		self.assertEqual(lines[1]["party"], "C1")
		self.assertNotIn("party", lines[0])

	def test_a_step_with_a_missing_account_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			cheques.posting_lines("Received", "clear", {"cheques_in_collection": "COLLECTION"})

	def test_every_step_balances_one_debit_against_one_credit(self):
		for cheque_type, step in (("Received", s) for s in ("submit", "deposit", "clear", "bounce", "endorse")):
			sides = [side for side, _ in entry(cheque_type, step)]
			self.assertEqual(sorted(sides), ["credit", "debit"])
