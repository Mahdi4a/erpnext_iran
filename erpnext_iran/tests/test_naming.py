import datetime
import unittest

from erpnext_iran import naming


class FakeDoc(dict):
	pass


class TestNaming(unittest.TestCase):
	def test_the_jalali_year_follows_the_date_of_the_document(self):
		doc = FakeDoc(posting_date="2026-03-20")
		self.assertEqual(naming.parse_variable(doc, "JY"), "1404")
		doc = FakeDoc(posting_date="2026-03-21")
		self.assertEqual(naming.parse_variable(doc, "JY"), "1405")
		self.assertEqual(naming.parse_variable(doc, "JYY"), "05")
		self.assertEqual(naming.parse_variable(doc, "JM"), "01")
		self.assertEqual(naming.parse_variable(doc, "JD"), "01")

	def test_a_transaction_date_is_used_when_there_is_no_posting_date(self):
		self.assertEqual(naming.parse_variable(FakeDoc(transaction_date="2027-03-21"), "JY"), "1406")

	def test_without_a_date_it_is_today(self):
		# today is the site's today (its time zone), not the server clock's: they differ for hours every night
		from frappe.utils import getdate

		self.assertEqual(naming.document_date(FakeDoc()), getdate())
		self.assertEqual(naming.document_date(None), getdate())


class TestJalaliSeries(unittest.TestCase):
	def run_add(self, options):
		from unittest.mock import MagicMock, patch

		meta = MagicMock()
		meta.get_field.return_value.options = options
		calls = []
		with (
			patch.object(naming.frappe, "only_for"),
			patch.object(naming.frappe, "get_meta", return_value=meta),
			patch.object(naming.frappe, "db", new=MagicMock()),
			patch.object(naming, "_set_series_property", side_effect=lambda d, prop, value: calls.append({"property": prop, "value": value})),
			patch.object(naming, "SERIES_DOCTYPES", ("Sales Invoice",)),
		):
			changed = naming.add_jalali_series()
		return changed, calls

	def test_a_jalali_series_is_added_before_each_gregorian_one_and_made_the_default(self):
		changed, calls = self.run_add("ACC-SINV-.YYYY.-\nACC-SINV-RET-.YYYY.-")

		self.assertEqual(changed, ["Sales Invoice"])
		by_property = {c["property"]: c["value"] for c in calls}
		self.assertEqual(
			by_property["options"],
			"ACC-SINV-.JY.-\nACC-SINV-RET-.JY.-\nACC-SINV-.YYYY.-\nACC-SINV-RET-.YYYY.-",
		)
		self.assertEqual(by_property["default"], "ACC-SINV-.JY.-")

	def test_a_document_that_already_has_the_jalali_series_is_left_alone(self):
		changed, calls = self.run_add("ACC-SINV-.JY.-\nACC-SINV-.YYYY.-")

		self.assertEqual(changed, [])
		self.assertEqual(calls, [])
