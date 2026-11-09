import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import pharmacy


def row(code, rate=100, factor=1, name=None):
	return frappe._dict(item_code=code, item_name=name or code, rate=rate, conversion_factor=factor)


class Doc:
	"""A sales invoice as the sale rules see it (a frappe._dict cannot hold an attribute called items)."""

	def __init__(self, rows, **fields):
		self.__dict__.update({"is_return": 0, "items": rows, "prescription_no": "", "prescriber_name": "", "patient_name": "", "patient_national_id": "", **fields})

	def get(self, key, default=None):
		return self.__dict__.get(key, default)


def invoice(*rows, **extra):
	return Doc(list(rows), **extra)


def flags(**by_code):
	defaults = {"requires_prescription": 0, "is_controlled_drug": 0, "approved_price": 0}
	return {code: frappe._dict({**defaults, "item_name": code, **values}) for code, values in by_code.items()}



def make_valid(nine="123456789"):
	total = sum(int(nine[i]) * (10 - i) for i in range(9))
	rest = total % 11
	return nine + str(rest if rest < 2 else 11 - rest)


class TestValidateSale(unittest.TestCase):
	def check(self, doc, drug_flags):
		with patch.object(pharmacy, "drug_flags", return_value=drug_flags):
			pharmacy.validate_sale(doc)

	def refused(self, doc, drug_flags):
		with self.assertRaises(frappe.ValidationError):
			self.check(doc, drug_flags)

	def test_a_sale_without_flagged_drugs_is_not_checked(self):
		self.check(invoice(row("A")), {})

	def test_a_return_asks_nothing(self):
		doc = invoice(row("A", rate=999))
		doc.is_return = 1
		self.check(doc, flags(A=dict(requires_prescription=1, approved_price=10)))

	def test_a_prescription_drug_needs_the_number_and_the_prescriber(self):
		f = flags(A=dict(requires_prescription=1))
		self.refused(invoice(row("A")), f)
		self.refused(invoice(row("A"), prescription_no="1"), f)
		self.refused(invoice(row("A"), prescriber_name="Dr"), f)
		self.refused(invoice(row("A"), prescription_no="  ", prescriber_name="Dr"), f)
		self.check(invoice(row("A"), prescription_no="1", prescriber_name="Dr"), f)

	def test_a_controlled_drug_needs_the_patient_and_a_valid_national_id(self):
		f = flags(A=dict(requires_prescription=1, is_controlled_drug=1))
		base = dict(prescription_no="1", prescriber_name="Dr")
		self.refused(invoice(row("A"), **base), f)
		self.refused(invoice(row("A"), patient_name="P", **base), f)
		self.refused(invoice(row("A"), patient_name="P", patient_national_id="0000000000", **base), f)
		self.refused(invoice(row("A"), patient_name="P", patient_national_id=make_valid()[:9] + "0" if make_valid()[9] != "0" else make_valid()[:9] + "1", **base), f)
		self.check(invoice(row("A"), patient_name="P", patient_national_id=make_valid(), **base), f)

	def test_a_controlled_drug_is_prescription_only_even_if_not_ticked_so(self):
		self.refused(invoice(row("A")), flags(A=dict(is_controlled_drug=1)))

	def test_the_approved_price_is_a_cap(self):
		f = flags(A=dict(approved_price=1000))
		self.check(invoice(row("A", rate=1000)), f)
		self.check(invoice(row("A", rate=1000.4)), f)  # half a rial of rounding
		self.check(invoice(row("A", rate=800)), f)
		self.refused(invoice(row("A", rate=1001)), f)

	def test_the_cap_is_per_unit_of_stock_not_per_box(self):
		f = flags(A=dict(approved_price=1000))
		self.check(invoice(row("A", rate=10000, factor=10)), f)  # a box of ten at 10,000 is 1,000 each
		self.refused(invoice(row("A", rate=12000, factor=10)), f)

	def test_a_drug_with_no_cap_may_be_sold_at_any_price(self):
		self.check(invoice(row("A", rate=10**9)), flags(B=dict(approved_price=1)))  # another drug is flagged, this one is not


class TestNationalIdAgreesWithTheJsCheck(unittest.TestCase):
	def test_python_validator_matches_the_algorithm_the_browser_uses(self):
		from iran_base.utils.validators import is_valid_national_id

		for nine in ("123456789", "000000001", "987654321", "246813579"):
			good = make_valid(nine)
			self.assertTrue(is_valid_national_id(good) or len(set(good)) == 1, good)
			bad = nine + str((int(good[9]) + 1) % 10)
			self.assertFalse(is_valid_national_id(bad), bad)
		self.assertFalse(is_valid_national_id("1111111111"))
		self.assertFalse(is_valid_national_id("12345"))


class TestFields(unittest.TestCase):
	def test_the_fields_exist_on_item_and_sales_invoice(self):
		item, invoice_meta = frappe.get_meta("Item"), frappe.get_meta("Sales Invoice")
		for field in ("generic_name", "drug_strength", "dosage_form", "irc_code", "requires_prescription", "is_controlled_drug", "approved_price"):
			self.assertTrue(item.has_field(field), field)
		for field in ("prescription_no", "prescriber_name", "prescriber_license", "patient_name", "patient_national_id"):
			self.assertTrue(invoice_meta.has_field(field), field)

	def test_a_prescription_is_not_copied_to_the_next_invoice(self):
		for field in ("prescription_no", "prescriber_name", "prescriber_license", "patient_name", "patient_national_id"):
			self.assertTrue(frappe.get_meta("Sales Invoice").get_field(field).no_copy, field)
