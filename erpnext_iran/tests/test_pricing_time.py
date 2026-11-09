import unittest
from datetime import datetime, time, timedelta

from erpnext_iran import pricing_time
from erpnext_iran.pricing_time import rule_applies

THURSDAY_11 = datetime(2026, 11, 12, 11, 0)  # 12 Nov 2026 is a Thursday
THURSDAY_13 = datetime(2026, 11, 12, 13, 0)
FRIDAY_11 = datetime(2026, 11, 13, 11, 0)


class TestRuleApplies(unittest.TestCase):
	def test_a_rule_with_no_limits_is_always_on(self):
		self.assertTrue(rule_applies({}, THURSDAY_11))
		self.assertTrue(rule_applies({"iran_from_time": None, "iran_to_time": ""}, FRIDAY_11))

	def test_days(self):
		rule = {"iran_thu": 1}
		self.assertTrue(rule_applies(rule, THURSDAY_11))
		self.assertFalse(rule_applies(rule, FRIDAY_11))

	def test_hours_use_a_closed_start_and_open_end(self):
		rule = {"iran_from_time": timedelta(hours=10), "iran_to_time": timedelta(hours=12)}
		self.assertTrue(rule_applies(rule, THURSDAY_11))
		self.assertTrue(rule_applies(rule, datetime(2026, 11, 12, 10, 0)))
		self.assertFalse(rule_applies(rule, datetime(2026, 11, 12, 12, 0)))
		self.assertFalse(rule_applies(rule, THURSDAY_13))

	def test_days_and_hours_together(self):
		rule = {"iran_thu": 1, "iran_from_time": "10:00:00", "iran_to_time": "12:00:00"}
		self.assertTrue(rule_applies(rule, THURSDAY_11))
		self.assertFalse(rule_applies(rule, THURSDAY_13))
		self.assertFalse(rule_applies(rule, FRIDAY_11))

	def test_a_night_window_crosses_midnight(self):
		rule = {"iran_from_time": time(22, 0), "iran_to_time": time(2, 0)}
		self.assertTrue(rule_applies(rule, datetime(2026, 11, 12, 23, 30)))
		self.assertTrue(rule_applies(rule, datetime(2026, 11, 12, 1, 0)))
		self.assertFalse(rule_applies(rule, THURSDAY_11))

	def test_only_a_start_or_only_an_end(self):
		self.assertTrue(rule_applies({"iran_from_time": "18:00:00"}, datetime(2026, 11, 12, 20, 0)))
		self.assertFalse(rule_applies({"iran_from_time": "18:00:00"}, THURSDAY_11))
		self.assertTrue(rule_applies({"iran_to_time": "12:00:00"}, THURSDAY_11))

	def test_install_is_idempotent(self):
		from erpnext.accounts.doctype.pricing_rule import utils

		pricing_time.install()
		first = utils.filter_pricing_rule_based_on_condition
		pricing_time.install()
		self.assertIs(utils.filter_pricing_rule_based_on_condition, first)
