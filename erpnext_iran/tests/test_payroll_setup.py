import unittest

import frappe

from erpnext_iran import payroll_setup


@unittest.skipUnless(frappe.db.exists("DocType", "Salary Component"), "HRMS is not installed")
class TestPayrollSetup(unittest.TestCase):
	def test_ensure_is_idempotent(self):
		payroll_setup.ensure_payroll()
		before = (frappe.db.count("Salary Component"), frappe.db.count("Salary Structure"))
		payroll_setup.ensure_payroll()
		self.assertEqual(before, (frappe.db.count("Salary Component"), frappe.db.count("Salary Structure")))

	def test_every_component_exists_with_its_abbreviation(self):
		payroll_setup.ensure_payroll()
		for name, abbr, kind, *_rest in payroll_setup.COMPONENTS:
			row = frappe.db.get_value("Salary Component", name, ["salary_component_abbr", "type"], as_dict=True)
			self.assertEqual((row.salary_component_abbr, row.type), (abbr, kind), name)

	def test_employer_costs_are_on_the_slip_but_outside_the_totals(self):
		payroll_setup.ensure_payroll()
		for name in ("بیمه سهم کارفرما", "بیمه بیکاری"):
			flags = frappe.db.get_value("Salary Component", name, ["do_not_include_in_total", "statistical_component"], as_dict=True)
			self.assertEqual((flags.do_not_include_in_total, flags.statistical_component), (1, 0))  # HRMS drops statistical rows
		self.assertEqual(frappe.db.get_value("Salary Component", "بیمه سهم کارگر", "do_not_include_in_total"), 0)

	def test_the_insurance_formulas_call_functions_hrms_knows(self):
		from hrms.payroll.utils import COMPONENT_EVAL_GLOBALS

		from erpnext_iran import iran_payroll

		iran_payroll.install()
		for name, _abbr, _kind, formula, *_rest in payroll_setup.COMPONENTS:
			for function in iran_payroll.FUNCTIONS:
				if function in formula:
					self.assertIn(function, COMPONENT_EVAL_GLOBALS, name)

	def test_a_company_has_its_structure_with_the_monthly_components(self):
		payroll_setup.ensure_payroll()
		company = frappe.get_all("Company", pluck="name")[0]
		name = payroll_setup.ensure_structure(company)
		doc = frappe.get_doc("Salary Structure", name)
		self.assertEqual(doc.docstatus, 1)
		abbrs = {row.abbr for row in [*doc.earnings, *doc.deductions]}
		self.assertEqual(abbrs, set(payroll_setup.IN_STRUCTURE))

	def test_shop_shifts_exist_once(self):
		payroll_setup.ensure_payroll()
		before = frappe.db.count("Shift Type")
		payroll_setup.ensure_payroll()
		self.assertEqual(before, frappe.db.count("Shift Type"))
		for name, start, end in payroll_setup.SHIFTS:
			self.assertTrue(frappe.db.exists("Shift Type", name), name)
