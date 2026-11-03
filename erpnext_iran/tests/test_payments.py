import unittest
from unittest.mock import patch

from erpnext_iran import payments


class TestPayments(unittest.TestCase):
	def test_toman_and_rial_are_each_others_rate(self):
		rates = {(a, b): rate for a, b, rate in payments.FIXED_RATES}
		self.assertEqual(rates[("IRT", "IRR")] * rates[("IRR", "IRT")], 1)

	def test_the_modes_are_bank_modes_with_persian_names(self):
		self.assertTrue(all(mode_type == "Bank" for mode_type in payments.PAYMENT_MODES.values()))

	def test_existing_modes_and_rates_are_not_made_again(self):
		with patch.object(payments.frappe, "db") as db, patch.object(payments.frappe, "new_doc") as new_doc:
			db.exists.return_value = True
			payments.ensure_payment_modes()
			payments.ensure_fixed_rates()
		new_doc.assert_not_called()


class TestDollarRate(unittest.TestCase):
	def run_it(self, existing):
		saved = []

		class Doc(dict):
			flags = type("Flags", (), {})()

			def update(self, values):
				super().update(values)

			def save(self):
				saved.append(dict(self))

		made = []

		def new_doc(doctype):
			made.append(Doc())
			return made[-1]

		with (
			patch.object(payments.frappe, "db") as db,
			patch.object(payments.frappe, "new_doc", side_effect=new_doc),
			patch.object(payments.frappe, "get_doc", side_effect=lambda *a: Doc()),
			patch.object(payments.frappe.utils, "today", return_value="2026-11-03"),
		):
			db.exists.return_value = True
			db.get_value.return_value = existing
			payments.save_dollar_rate(1_000_000)
		return saved

	def test_the_rate_is_saved_to_the_rial_and_to_the_toman(self):
		saved = self.run_it(existing=None)

		self.assertEqual([(d["to_currency"], d["exchange_rate"]) for d in saved], [("IRR", 1_000_000), ("IRT", 100_000)])
		self.assertTrue(all(d["from_currency"] == "USD" and d["date"] == "2026-11-03" for d in saved))

	def test_a_rate_of_today_that_exists_is_changed_not_added(self):
		with patch.object(payments.frappe, "new_doc") as new_doc:
			self.run_it(existing="2026-11-03-USD-IRR")
		new_doc.assert_not_called()
