"""The salary components and the salary structure of Iranian payroll, made when Frappe HR is installed.

They are a starting point: the accountant edits the formulas (which allowances insurance is taken on, which are
tax-exempt) in the Salary Component and Salary Structure like any other. Existing ones are left as edited."""

from __future__ import annotations

import frappe

STRUCTURE = "ساختار حقوق ایران"

# name, abbreviation, type, formula, depends on payment days, outside the total (shown on the slip, not deducted:
# the employer's own cost. HRMS does not put a statistical component on the slip at all, so it is not used.)
COMPONENTS = [
	("حقوق پایه", "BASE", "Earning", "base", 1, 0),
	("حق مسکن", "HSG", "Earning", "iran_housing", 1, 0),
	("حق خواروبار", "FOOD", "Earning", "iran_food", 1, 0),
	("حق اولاد", "CHILD", "Earning", "iran_child_allowance(iran_children, end_date)", 0, 0),
	("بیمه سهم کارگر", "EINS", "Deduction", "iran_employee_insurance(BASE + HSG + FOOD, end_date) if iran_insurance_applies else 0", 0, 0),
	("بیمه سهم کارفرما", "EMPINS", "Deduction", "iran_employer_insurance(BASE + HSG + FOOD, end_date) if iran_insurance_applies else 0", 0, 1),
	("بیمه بیکاری", "UNEMP", "Deduction", "iran_unemployment(BASE + HSG + FOOD, end_date) if iran_insurance_applies else 0", 0, 1),
	("مالیات حقوق", "ITAX", "Deduction", "", 0, 0),
	("عیدی", "EIDI", "Earning", "", 0, 0),
	("سنوات", "SANAVAT", "Earning", "", 0, 0),
	("اضافه‌کار", "OT", "Earning", "", 0, 0),
]
# the ones a monthly structure carries; the others are added to a slip as Additional Salary
IN_STRUCTURE = ("BASE", "HSG", "FOOD", "CHILD", "EINS", "EMPINS", "UNEMP", "ITAX")


def ensure_component(name: str, abbr: str, kind: str, formula: str, payment_days: int, outside_total: int) -> str:
	if frappe.db.exists("Salary Component", name):
		return name
	doc = frappe.new_doc("Salary Component")
	doc.update(
		{
			"salary_component": name,
			"salary_component_abbr": abbr,
			"type": kind,
			"depends_on_payment_days": payment_days,
			"do_not_include_in_total": outside_total,
			"amount_based_on_formula": 1 if formula else 0,
			"formula": formula,
		}
	)
	if name == "مالیات حقوق":
		doc.variable_based_on_taxable_salary = 1
	if kind == "Earning":
		doc.is_tax_applicable = 1
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def ensure_structure(company: str):
	name = f"{STRUCTURE} - {frappe.get_cached_value('Company', company, 'abbr')}"
	if frappe.db.exists("Salary Structure", name):
		return name
	structure = frappe.new_doc("Salary Structure")
	structure.update(
		{
			"name": name,
			"company": company,
			"payroll_frequency": "Monthly",
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"is_active": "Yes",
		}
	)
	for label, abbr, kind, formula, _days, _stat in COMPONENTS:
		if abbr not in IN_STRUCTURE:
			continue
		row = {"salary_component": label, "abbr": abbr, "amount_based_on_formula": 1 if formula else 0, "formula": formula}
		structure.append("earnings" if kind == "Earning" else "deductions", row)
	structure.flags.ignore_permissions = True
	structure.insert()
	structure.submit()
	return structure.name


def ensure_payroll():
	"""Components for every site with HRMS, and a structure for every company."""
	if not (frappe.db.exists("DocType", "Salary Component") and frappe.db.exists("DocType", "Iran Payroll Settings")):
		return
	for spec in COMPONENTS:
		ensure_component(*spec)
	for company in frappe.get_all("Company", pluck="name"):
		ensure_structure(company)
