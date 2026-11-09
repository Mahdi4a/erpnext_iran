import unittest

from jinja2 import Environment

from erpnext_iran import print_formats


class TestPrintFormats(unittest.TestCase):
	def test_every_document_has_a_format_that_compiles_and_reads_right_to_left(self):
		formats = {k: v for k, v in print_formats.formats().items() if k != "Iran POS Receipt"}

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
		self.assertLess(buyer, html.index("{{ doc.company | e }}", buyer))

	def test_free_text_of_the_document_is_escaped(self):
		"""Names typed by people (items, parties, tax and payment rows) go through |e; the Text Editor fields (terms,
		remarks, item description) are HTML by design and are sanitised when saved."""
		import re

		for doctype in print_formats.DOCUMENTS:
			html = print_formats.build_document_html(doctype)
			for expression in re.findall(r"\{\{[^}]*\}\}", html):
				if re.search(r"row\.item_name|doc\.company\b(?!_)|row\.uom|\bparty_name", expression):
					self.assertIn("| e", expression, expression)

	def test_the_pos_receipt_escapes_names_too(self):
		import re

		from erpnext_iran import pos_receipt

		html = pos_receipt.build_receipt_html()
		for needle in ("row.item_name", "doc.customer_name", "tax.description", "pay.mode_of_payment", "doc.company", "doc.pos_profile"):
			matches = re.findall(r"\{\{[^}]*" + re.escape(needle) + r"[^}]*\}\}", html)
			self.assertTrue(matches, needle)
			for match in matches:
				self.assertIn("| e", match, match)

	def test_a_quotation_takes_its_customer_from_the_party_name_field(self):
		html = print_formats.build_document_html("Quotation")

		self.assertIn('doc.get("party_name")', html)
		self.assertIn("transaction_date", html)
		self.assertIn("valid_till", html)
