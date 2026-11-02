import unittest
from unittest.mock import patch

from erpnext_iran import in_words


class FakeMeta:
	def __init__(self, *fields):
		self.fields = set(fields)

	def has_field(self, fieldname):
		return fieldname in self.fields


class FakeDoc(dict):
	def __init__(self, doctype, meta, **values):
		super().__init__(values)
		self.doctype = doctype
		self.meta = meta

	def set(self, key, value):
		self[key] = value

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError:
			raise AttributeError(name) from None


def invoice(**values):
	meta = FakeMeta("in_words", "base_in_words", "rounded_total", "base_rounded_total")
	return FakeDoc("Sales Invoice", meta, currency="IRR", company_currency="IRR", **values)


class TestInWords(unittest.TestCase):
	def setUp(self):
		for patcher in (
			patch.object(in_words.frappe.local, "lang", "fa", create=True),
			patch.object(in_words.frappe, "_", side_effect=lambda text, context=None: "فقط {0}."),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_the_unit_follows_the_words(self):
		self.assertEqual(
			in_words.money_in_persian(1250000, "IRR"), "فقط یک میلیون و دویست و پنجاه هزار ریال."
		)
		self.assertEqual(in_words.money_in_persian(21, "IRT"), "فقط بیست و یک تومان.")
		self.assertEqual(in_words.money_in_persian(0, "IRR"), "فقط صفر ریال.")

	def test_the_rounded_total_is_written_and_a_negative_amount_reads_as_positive(self):
		doc = invoice(rounded_total=-5000, base_rounded_total=-5000, grand_total=-4999.6, base_grand_total=-4999.6)

		in_words.set_in_words(doc)

		self.assertEqual(doc["in_words"], "فقط پنج هزار ریال.")
		self.assertEqual(doc["base_in_words"], "فقط پنج هزار ریال.")

	def test_the_grand_total_is_written_when_rounding_is_off(self):
		doc = invoice(rounded_total=0, base_rounded_total=0, grand_total=2000, base_grand_total=2000)
		doc.is_rounded_total_disabled = lambda: True

		in_words.set_in_words(doc)

		self.assertEqual(doc["in_words"], "فقط دو هزار ریال.")

	def test_other_currencies_and_other_languages_are_left_alone(self):
		doc = invoice(rounded_total=100, base_rounded_total=100, in_words="One Hundred Dollars only.")
		doc["currency"] = "USD"
		doc["company_currency"] = "USD"
		in_words.set_in_words(doc)
		self.assertEqual(doc["in_words"], "One Hundred Dollars only.")

		doc["currency"] = "IRR"
		with patch.object(in_words.frappe.local, "lang", "en"):
			in_words.set_in_words(doc)
		self.assertEqual(doc["in_words"], "One Hundred Dollars only.")

	def test_a_payment_entry_follows_the_direction_of_the_payment(self):
		meta = FakeMeta("in_words", "base_in_words")
		doc = FakeDoc(
			"Payment Entry",
			meta,
			payment_type="Receive",
			received_amount=3000,
			base_received_amount=3000,
			paid_to_account_currency="IRR",
			company_currency="IRR",
		)

		in_words.set_in_words(doc)

		self.assertEqual(doc["in_words"], "فقط سه هزار ریال.")
