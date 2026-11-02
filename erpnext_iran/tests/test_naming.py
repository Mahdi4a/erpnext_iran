import datetime
import unittest

from erpnext_iran import naming


class FakeDoc(dict):
	pass


class TestNaming(unittest.TestCase):
	def test_the_jalali_year_follows_the_date_of_the_document(self):
		doc = FakeDoc(posting_date="2026-03-20")
		self.assertEqual(naming.parse_variable(doc, "JY"), "1404")
		doc = FakeDoc(posting_date="2026-03-21")
		self.assertEqual(naming.parse_variable(doc, "JY"), "1405")
		self.assertEqual(naming.parse_variable(doc, "JYY"), "05")
		self.assertEqual(naming.parse_variable(doc, "JM"), "01")
		self.assertEqual(naming.parse_variable(doc, "JD"), "01")

	def test_a_transaction_date_is_used_when_there_is_no_posting_date(self):
		self.assertEqual(naming.parse_variable(FakeDoc(transaction_date="2027-03-21"), "JY"), "1406")

	def test_without_a_date_it_is_today(self):
		self.assertEqual(naming.document_date(FakeDoc()), datetime.date.today())
		self.assertEqual(naming.document_date(None), datetime.date.today())
