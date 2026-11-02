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
