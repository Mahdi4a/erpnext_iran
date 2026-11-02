import unittest

from jinja2 import Environment

from erpnext_iran import print_formats


class TestPrintFormats(unittest.TestCase):
	def test_every_document_has_a_format_that_compiles_and_reads_right_to_left(self):
		formats = print_formats.formats()

		self.assertEqual(
			{doctype for doctype, _html in formats.values()},
			{"Purchase Invoice", "Quotation", "Sales Order", "Delivery Note", "Payment Entry"},
		)
		for name, (_doctype, html) in formats.items():
			with self.subTest(name):
				Environment().parse(html)
				self.assertIn("direction: rtl", html)
				self.assertIn("| jalali_date", html)
				self.assertIn("| iran_digits", html)
				self.assertIn("doc.in_words", html)

	def test_a_purchase_invoice_names_the_supplier_as_the_seller_and_the_company_as_the_buyer(self):
		html = print_formats.build_document_html("Purchase Invoice")

		seller = html.index("مشخصات فروشنده")
		buyer = html.index("مشخصات خریدار")
		self.assertLess(html.index("doc.supplier_name", seller), buyer)
		self.assertLess(buyer, html.index("{{ doc.company }}", buyer))

	def test_a_quotation_takes_its_customer_from_the_party_name_field(self):
		html = print_formats.build_document_html("Quotation")

		self.assertIn('doc.get("party_name")', html)
		self.assertIn("transaction_date", html)
		self.assertIn("valid_till", html)
