import unittest

from erpnext_iran import chart_of_accounts

ROOT_TYPES = {"Asset", "Liability", "Equity", "Income", "Expense"}
METADATA = {"account_number", "account_type", "root_type", "is_group", "account_category", "tax_rate"}


def walk(tree):
	for name, child in tree.items():
		if name in METADATA:
			continue
		yield name, child
		yield from walk(child)


class TestChartOfAccounts(unittest.TestCase):
	def setUp(self):
		self.chart = chart_of_accounts.load_chart()
		self.tree = self.chart["tree"]

	def test_the_chart_has_the_name_the_company_form_offers(self):
		self.assertEqual(self.chart["name"], chart_of_accounts.CHART_NAME)
		self.assertEqual(self.chart["country_code"], "ir")

	def test_there_is_one_root_per_root_type(self):
		self.assertEqual({root["root_type"] for root in self.tree.values()}, ROOT_TYPES)
		self.assertEqual(len(self.tree), len(ROOT_TYPES))

	def test_account_numbers_are_unique_digits(self):
		numbers = [c["account_number"] for _, c in walk(self.tree) if "account_number" in c]
		self.assertTrue(all(n.isdigit() for n in numbers))
		self.assertEqual(len(numbers), len(set(numbers)))

	def test_a_child_code_starts_with_its_parent_code(self):
		def check(node, parent_number):
			for name, child in node.items():
				if name in METADATA:
					continue
				number = child.get("account_number", "")
				if parent_number and number:
					self.assertTrue(number.startswith(parent_number), f"{name}: {number} under {parent_number}")
				check(child, number or parent_number)

		check(self.tree, "")

	def test_the_account_types_erpnext_needs_for_a_company_exist(self):
		types = {c.get("account_type") for _, c in walk(self.tree)}
		needed = {
			"Receivable", "Payable", "Cash", "Bank", "Stock", "Tax", "Round Off", "Depreciation",
			"Accumulated Depreciation", "Cost of Goods Sold", "Stock Adjustment",
			"Stock Received But Not Billed", "Asset Received But Not Billed",
			"Expenses Included In Valuation", "Capital Work in Progress", "Temporary", "Fixed Asset",
		}
		self.assertEqual(needed - types, set())
