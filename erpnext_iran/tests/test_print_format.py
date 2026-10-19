import json
import unittest
from pathlib import Path

from jinja2 import Environment

PRINT_FORMAT = (
	Path(__file__).parent.parent / "erpnext_iran" / "print_format" / "iran_sales_invoice" / "iran_sales_invoice.json"
)


class TestIranSalesInvoicePrintFormat(unittest.TestCase):
	def setUp(self):
		self.doc = json.loads(PRINT_FORMAT.read_text(encoding="utf-8"))

	def test_it_is_a_standard_jinja_format_of_the_sales_invoice(self):
		self.assertEqual(self.doc["doctype"], "Print Format")
		self.assertEqual(self.doc["doc_type"], "Sales Invoice")
		self.assertEqual(self.doc["standard"], "Yes")
		self.assertEqual(self.doc["print_format_type"], "Jinja")
		self.assertEqual(self.doc["module"], "Erpnext Iran")

	def test_the_template_compiles_and_is_right_to_left(self):
		Environment().parse(self.doc["html"])
		self.assertIn("direction: rtl", self.doc["html"])

	def test_numbers_and_dates_go_through_the_iran_filters(self):
		self.assertIn("| jalali_date", self.doc["html"])
		self.assertIn("| iran_digits", self.doc["html"])
