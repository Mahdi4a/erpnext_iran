import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from erpnext_iran import branches


class TestBranches(unittest.TestCase):
	def test_a_branch_without_its_own_list_sells_at_the_standard_prices(self):
		with patch.object(branches.frappe, "new_doc") as new_doc:
			self.assertEqual(branches.ensure_price_list("Valiasr", "Test Company", 0), "Standard Selling")
		new_doc.assert_not_called()

	def test_an_existing_warehouse_and_cost_center_are_linked_not_made_again(self):
		with patch.object(branches.frappe, "db", MagicMock()) as db, patch.object(branches.frappe, "new_doc") as new_doc:
			db.get_value.return_value = "Valiasr - TC"
			self.assertEqual(branches.ensure_warehouse("Valiasr", "Test Company"), "Valiasr - TC")
			self.assertEqual(branches.ensure_cost_center("Valiasr", "Test Company"), "Valiasr - TC")
		new_doc.assert_not_called()

	def test_a_new_warehouse_goes_under_the_stores_group(self):
		made = MagicMock(name="Valiasr - TC")
		made.name = "Valiasr - TC"
		with patch.object(branches.frappe, "db", MagicMock()) as db, patch.object(branches.frappe, "new_doc", return_value=made):
			db.get_value.side_effect = [None, "Stores - TC"]
			branches.ensure_warehouse("Valiasr", "Test Company")
		made.update.assert_called_once_with(
			{"warehouse_name": "Valiasr", "company": "Test Company", "parent_warehouse": "Stores - TC"}
		)
		made.insert.assert_called_once()

	def test_a_mode_of_payment_without_a_company_account_is_skipped(self):
		with patch.object(branches.frappe, "db", MagicMock()) as db, patch.object(branches.frappe, "get_cached_value", return_value=None):
			db.exists.return_value = True
			self.assertIsNone(branches.ensure_mode_account("کارت‌خوان", "Test Company"))

	def test_cash_posts_to_the_cash_account_and_cards_to_the_bank_account(self):
		asked = []
		with (
			patch.object(branches.frappe, "db", MagicMock()) as db,
			patch.object(branches.frappe, "get_cached_value", side_effect=lambda d, c, f: asked.append(f) or "acc"),
			patch.object(branches.frappe, "get_doc", return_value=SimpleNamespace(accounts=[SimpleNamespace(company="Test Company")])),
		):
			db.exists.return_value = True
			branches.ensure_mode_account("Cash", "Test Company")
			branches.ensure_mode_account("کارت‌خوان", "Test Company")
		self.assertEqual(asked, ["default_cash_account", "default_bank_account"])

	def test_the_pos_cannot_be_made_for_a_company_that_cannot_take_any_payment(self):
		branch = SimpleNamespace(branch_name="Valiasr", company="Test Company")
		with (
			patch.object(branches.frappe, "db", MagicMock()) as db,
			patch.object(branches.frappe, "get_cached_doc"),
			patch.object(branches, "ensure_mode_account", return_value=None),
			patch.object(branches.frappe, "throw", side_effect=Exception("no account")),
		):
			db.exists.return_value = False
			with self.assertRaises(Exception):
				branches.ensure_pos_profile(branch)


class TestDefaultIncomeAccount(unittest.TestCase):
	def run_it(self, current, account):
		from erpnext_iran import setup

		db = MagicMock()
		db.get_value.side_effect = [current] if current else [None, account]
		with patch.object(setup.frappe, "db", db):
			setup.ensure_default_income_account("Test Company")
		return db

	def test_an_empty_default_gets_domestic_sales(self):
		db = self.run_it(None, "410101 - X - TC")
		db.set_value.assert_called_once_with("Company", "Test Company", "default_income_account", "410101 - X - TC")

	def test_a_chosen_default_is_kept(self):
		self.run_it("4102 - Y - TC", None).set_value.assert_not_called()

	def test_a_chart_without_that_account_changes_nothing(self):
		self.run_it(None, None).set_value.assert_not_called()


class TestPosReceipt(unittest.TestCase):
	def test_the_receipt_is_a_print_format_of_the_sales_invoice(self):
		from erpnext_iran import print_formats

		doctype, html = print_formats.formats()["Iran POS Receipt"]
		self.assertEqual(doctype, "Sales Invoice")
		from jinja2 import Environment

		Environment().parse(html)
		self.assertIn("80mm", html)
		self.assertIn("direction: rtl", html)
		self.assertIn("jalali_date", html)


class TestWalkInCustomer(unittest.TestCase):
	def test_an_existing_walk_in_customer_is_reused(self):
		with patch.object(branches.frappe, "db", MagicMock()) as db, patch.object(branches.frappe, "new_doc") as new_doc:
			db.exists.return_value = True
			self.assertEqual(branches.ensure_walk_in_customer(), branches.WALK_IN_CUSTOMER)
		new_doc.assert_not_called()

	def test_a_new_one_is_an_individual_in_a_leaf_group_and_territory(self):
		made = MagicMock()
		made.name = branches.WALK_IN_CUSTOMER
		with patch.object(branches.frappe, "db", MagicMock()) as db, patch.object(branches.frappe, "new_doc", return_value=made):
			db.exists.return_value = False
			db.get_value.side_effect = ["Individual", "Iran"]
			branches.ensure_walk_in_customer()
		values = made.update.call_args.args[0]
		self.assertEqual(values["customer_type"], "Individual")
		self.assertEqual((values["customer_group"], values["territory"]), ("Individual", "Iran"))
		made.insert.assert_called_once()

	def test_an_existing_profile_without_a_customer_gets_the_walk_in_customer(self):
		branch = SimpleNamespace(branch_name="Valiasr")
		with (
			patch.object(branches.frappe, "db", MagicMock()) as db,
			patch.object(branches, "ensure_walk_in_customer", return_value="W"),
		):
			db.exists.return_value = True
			db.get_value.return_value = None
			branches.ensure_pos_profile(branch)
		db.set_value.assert_called_once()
		self.assertEqual(db.set_value.call_args.args[2:], ("customer", "W"))


class TestFastTill(unittest.TestCase):
	def test_a_new_profile_adds_a_scan_to_the_cart_and_prints_the_receipt(self):
		self.assertEqual(branches.FAST_TILL["auto_add_item_to_cart"], 1)
		self.assertEqual(branches.FAST_TILL["print_receipt_on_order_complete"], 1)
		self.assertEqual(branches.FAST_TILL["action_on_new_invoice"], "Save Changes and Load New Invoice")

	def test_a_sale_is_completed_without_the_submit_question(self):
		self.assertEqual(branches.FAST_TILL["skip_submit_confirmation"], 1)

	def test_the_receipt_of_a_branch_is_the_persian_80_mm_one(self):
		self.assertEqual(branches.FAST_TILL["print_format"], "Iran POS Receipt")
