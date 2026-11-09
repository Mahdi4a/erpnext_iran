import datetime
import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import iran_payroll as ip

ROW = frappe._dict(
	jalali_year=1405, employee_insurance_pct=7, employer_insurance_pct=20, unemployment_pct=3,
	insurance_ceiling=100_000_000, child_allowance=1_000_000, eidi_days=60, eidi_cap_days=90, min_daily_wage=2_000_000, sanavat_days=30,
)


def with_row(row=ROW):
	return patch.object(ip, "year_row", return_value=row)


class TestInsurance(unittest.TestCase):
	def test_shares_are_percentages_of_the_insurable_pay(self):
		with with_row():
			self.assertEqual(ip.employee_insurance(10_000_000), 700_000)
			self.assertEqual(ip.employer_insurance(10_000_000), 2_000_000)
			self.assertEqual(ip.unemployment_insurance(10_000_000), 300_000)

	def test_the_ceiling_caps_the_insurable_pay(self):
		with with_row():
			self.assertEqual(ip.insurable(150_000_000), 100_000_000)
			self.assertEqual(ip.employee_insurance(150_000_000), 7_000_000)

	def test_no_ceiling_means_no_cap(self):
		with with_row(frappe._dict(ROW, insurance_ceiling=0)):
			self.assertEqual(ip.insurable(150_000_000), 150_000_000)

	def test_negative_or_empty_pay_is_nothing(self):
		with with_row():
			self.assertEqual(ip.insurable(-5), 0)
			self.assertEqual(ip.employee_insurance(0), 0)

	def test_an_empty_rate_is_an_error_not_zero(self):
		with with_row(frappe._dict(ROW, employee_insurance_pct=None)):
			with self.assertRaises(frappe.ValidationError):
				ip.employee_insurance(1_000_000)

	def test_children_allowance(self):
		with with_row():
			self.assertEqual(ip.child_allowance(2), 2_000_000)
			self.assertEqual(ip.child_allowance(0), 0)
			self.assertEqual(ip.child_allowance(None), 0)
			self.assertEqual(ip.child_allowance(-1), 0)


class TestYearRow(unittest.TestCase):
	def test_the_row_of_the_year_is_chosen_by_the_jalali_year_of_the_date(self):
		settings = frappe._dict(years=[frappe._dict(jalali_year=1404, as_dict=lambda: {"jalali_year": 1404}), frappe._dict(jalali_year=1405, as_dict=lambda: {"jalali_year": 1405})])
		with patch.object(ip.frappe, "get_cached_doc", return_value=settings):
			self.assertEqual(ip.year_row(datetime.date(2026, 4, 1)).jalali_year, 1405)  # 12 Farvardin 1405
			self.assertEqual(ip.year_row(datetime.date(2026, 3, 1)).jalali_year, 1404)  # Esfand 1404

	def test_a_year_with_no_row_is_refused(self):
		with patch.object(ip.frappe, "get_cached_doc", return_value=frappe._dict(years=[])):
			with self.assertRaises(frappe.ValidationError):
				ip.year_row(datetime.date(2026, 4, 1))


class TestEidiAndSeniority(unittest.TestCase):
	def test_eidi_is_the_days_of_wage_capped_by_minimum_wage_days(self):
		with with_row(), patch.object(ip.frappe.db, "get_value", return_value=datetime.date(2020, 1, 1)), patch.object(ip, "daily_wage", return_value=1_000_000):
			result = ip.eidi_amount("E", 1405)
		self.assertEqual(result["amount"], 60_000_000)  # 60 days x 1,000,000; the cap is 90 x 2,000,000

	def test_the_cap_applies(self):
		with with_row(), patch.object(ip.frappe.db, "get_value", return_value=datetime.date(2020, 1, 1)), patch.object(ip, "daily_wage", return_value=5_000_000):
			self.assertEqual(ip.eidi_amount("E", 1405)["amount"], 180_000_000)  # 90 x 2,000,000, not 60 x 5,000,000

	def test_eidi_is_in_proportion_to_the_months_worked(self):
		from erpnext_iran.jalali import fiscal_year_dates

		start, end = fiscal_year_dates(1405)
		half = start + (end - start) / 2
		with with_row(), patch.object(ip.frappe.db, "get_value", return_value=half), patch.object(ip, "daily_wage", return_value=1_000_000):
			share = ip.eidi_amount("E", 1405)["share_of_year"]
		self.assertAlmostEqual(share, 0.5, delta=0.01)

	def test_eidi_needs_its_days_in_the_settings(self):
		with with_row(frappe._dict(ROW, eidi_days=0)):
			with self.assertRaises(frappe.ValidationError):
				ip.eidi_amount("E", 1405)

	def test_seniority_is_years_times_days_times_the_daily_wage(self):
		with with_row(), patch.object(ip.frappe.db, "get_value", return_value=datetime.date(2016, 4, 1)), patch.object(ip, "daily_wage", return_value=1_000_000):
			result = ip.seniority_amount("E", datetime.date(2026, 4, 1))
		self.assertAlmostEqual(result["years"], 10.0, delta=0.05)
		self.assertAlmostEqual(result["amount"], 300_000_000, delta=2_000_000)


class TestFormulaFunctions(unittest.TestCase):
	def test_the_functions_are_available_to_salary_formulas(self):
		try:
			from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS
		except ImportError:
			self.skipTest("HRMS is not installed")
		ip.install()
		for name in ip.FUNCTIONS:
			self.assertIn(name, COMPONENT_EVAL_GLOBALS)
