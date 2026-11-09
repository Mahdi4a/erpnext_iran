import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import discount


def row(list_price, rate, qty=1, rules=None):
	return frappe._dict(price_list_rate=list_price, rate=rate, qty=qty, pricing_rules=rules)


class TestDiscountPercent(unittest.TestCase):
	def test_no_discount(self):
		self.assertEqual(discount.discount_percent(frappe._dict(items=[row(100, 100)])), 0)

	def test_line_discount_over_all_lines(self):
		doc = frappe._dict(items=[row(100, 90), row(100, 100)])
		self.assertAlmostEqual(discount.discount_percent(doc), 5)

	def test_whole_invoice_discount_counts(self):
		doc = frappe._dict(items=[row(1000, 1000)], discount_amount=100)
		self.assertAlmostEqual(discount.discount_percent(doc), 10)

	def test_a_pricing_rule_promotion_does_not_count(self):
		doc = frappe._dict(items=[row(100, 80, rules='["PRLE-1"]'), row(100, 95)])
		self.assertAlmostEqual(discount.discount_percent(doc), 2.5)

	def test_a_price_above_the_list_is_not_a_negative_discount(self):
		self.assertEqual(discount.discount_percent(frappe._dict(items=[row(100, 120)])), 0)


class TestCheckDiscount(unittest.TestCase):
	def invoice(self, **extra):
		return frappe._dict(is_pos=1, pos_profile="P", items=[row(100, 80)], **extra)  # 20 % off

	def run_check(self, doc, limit, manager=False, cached=None):
		with patch.object(discount.frappe.db, "get_value", return_value=limit), patch.object(
			discount, "is_manager", return_value=manager
		), patch.object(discount.frappe.cache, "get_value", return_value=cached):
			discount.check_discount(doc)

	def test_within_the_limit(self):
		self.run_check(self.invoice(), 25)

	def test_over_the_limit_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_check(self.invoice(), 10)

	def test_no_limit_means_no_check(self):
		self.run_check(self.invoice(), 100)
		self.run_check(self.invoice(), 0)

	def test_a_manager_may_go_over(self):
		self.run_check(self.invoice(), 10, manager=True)

	def test_a_valid_approval_token_lets_it_through_and_is_recorded(self):
		doc = self.invoice(discount_approval_token="abc")
		self.run_check(doc, 10, cached={"manager": "boss@example.com", "cashier": frappe.session.user})
		self.assertEqual(doc.discount_approved_by, "boss@example.com")

	def test_a_token_made_for_another_cashier_is_no_approval(self):
		doc = self.invoice(discount_approval_token="abc")
		with self.assertRaises(frappe.ValidationError):
			self.run_check(doc, 10, cached={"manager": "boss@example.com", "cashier": "someone.else@example.com"})

	def test_an_old_style_token_without_a_cashier_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_check(self.invoice(discount_approval_token="abc"), 10, cached="boss@example.com")

	def test_the_token_is_spent_with_the_sale(self):
		doc = self.invoice(discount_approval_token="abc")
		with patch.object(discount.frappe.cache, "delete_value") as delete:
			discount.consume_token(doc)
			discount.consume_token(self.invoice())  # a sale without a token spends nothing
		delete.assert_called_once_with(discount.token_key("abc"))

	def test_an_expired_token_does_not(self):
		with self.assertRaises(frappe.ValidationError):
			self.run_check(self.invoice(discount_approval_token="abc"), 10, cached=None)

	def test_an_invoice_that_is_not_a_pos_sale_is_not_checked(self):
		doc = frappe._dict(is_pos=0, pos_profile="", items=[row(100, 50)])
		self.run_check(doc, 10)


class TestIsManager(unittest.TestCase):
	def test_roles(self):
		with patch.object(discount.frappe, "get_roles", return_value=["Sales User"]):
			self.assertFalse(discount.is_manager("cashier@example.com"))
		with patch.object(discount.frappe, "get_roles", return_value=["Sales User", "Sales Manager"]):
			self.assertTrue(discount.is_manager("boss@example.com"))
		self.assertTrue(discount.is_manager("Administrator"))


class TestApproveDiscount(unittest.TestCase):
	"""A wrong password must come back as a plain validation error, never a 401 that logs the cashier out."""

	def test_wrong_user_and_wrong_password_are_validation_errors(self):
		with self.assertRaises(frappe.ValidationError) as unknown:
			discount.approve_discount("nobody@example.com", "x")
		self.assertNotIsInstance(unknown.exception, frappe.AuthenticationError)

		with patch.object(discount.frappe.db, "get_value", return_value="manager1"), patch(
			"frappe.utils.password.check_password", side_effect=frappe.AuthenticationError
		):
			with self.assertRaises(frappe.ValidationError) as wrong:
				discount.approve_discount("manager1", "bad")
		self.assertNotIsInstance(wrong.exception, frappe.AuthenticationError)


class TestApprovalLockout(unittest.TestCase):
	def test_five_wrong_passwords_lock_the_manager_for_a_while(self):
		from frappe.auth import LoginAttemptTracker

		key = "discount_approval:lockout-test@example.com"
		tracker = LoginAttemptTracker(key, max_consecutive_login_attempts=5, lock_interval=300)
		tracker.add_success_attempt()
		try:
			with patch.object(discount.frappe.db, "get_value", return_value="lockout-test@example.com"), patch(
				"frappe.utils.password.check_password", side_effect=frappe.AuthenticationError
			):
				for _attempt in range(6):
					with self.assertRaises(frappe.ValidationError):
						discount.approve_discount("lockout-test@example.com", "bad")
			self.assertFalse(tracker.is_user_allowed())
			with self.assertRaises(frappe.ValidationError) as locked:
				discount.approve_discount("lockout-test@example.com", "even-the-right-one")
			self.assertIn("Too many", str(locked.exception))
		finally:
			tracker.add_success_attempt()
