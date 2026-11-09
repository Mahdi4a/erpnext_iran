import unittest
import unittest.mock
from unittest.mock import patch

from erpnext_iran import defaults


class FakeDoc(dict):
	def set(self, key, value):
		self[key] = value


class TestDefaults(unittest.TestCase):
	def test_persian_digits_filter_changes_only_digits(self):
		self.assertEqual(defaults.persian_digits("1,250,000 IRR"), "۱,۲۵۰,۰۰۰ IRR")

	def test_an_iranian_company_without_a_currency_gets_the_rial(self):
		doc = FakeDoc(country="Iran")
		with patch.object(defaults, "ensure_currency") as ensure:
			defaults.set_company_currency(doc)

		self.assertEqual(doc["default_currency"], "IRR")
		ensure.assert_called_once_with("IRR")

	def test_a_chosen_currency_or_another_country_is_left_alone(self):
		for doc in (FakeDoc(country="Iran", default_currency="IRT"), FakeDoc(country="Germany")):
			with patch.object(defaults, "ensure_currency") as ensure:
				defaults.set_company_currency(doc)
			ensure.assert_not_called()
		self.assertEqual(doc.get("default_currency"), None)

	def test_stock_system_settings_are_changed_but_chosen_ones_are_kept(self):
		settings = {
			"number_format": "#,###.##",
			"currency_precision": "2",
			"first_day_of_the_week": "Monday",
			"time_zone": "Europe/Berlin",
			"language": "en",
		}
		db = unittest.mock.MagicMock()
		db.get_single_value.side_effect = lambda doctype, fieldname: settings.get(fieldname)
		db.set_single_value.side_effect = lambda doctype, fieldname, value: settings.update({fieldname: value})

		with (
			patch.object(defaults.frappe, "db", db),
			patch.object(defaults.frappe, "clear_cache"),
			patch("frappe.translate.set_default_language") as set_language,
		):
			defaults.apply_system_defaults()

		db.set_default.assert_any_call("number_format", "#,###")
		db.set_default.assert_any_call("currency_precision", "0")
		set_language.assert_called_once_with("fa")
		self.assertEqual(settings["number_format"], "#,###")
		self.assertEqual(settings["currency_precision"], "0")
		self.assertEqual(settings["first_day_of_the_week"], "Saturday")
		self.assertEqual(settings["time_zone"], "Europe/Berlin")
		self.assertEqual(settings["language"], "fa")


class TestTimeZone(unittest.TestCase):
	def run_with(self, current):
		from unittest.mock import patch

		with patch.object(defaults.frappe.db, "get_single_value", return_value=current), patch.object(
			defaults.frappe.db, "set_single_value"
		) as set_value, patch.object(defaults.frappe.db, "set_default"), patch.object(defaults.frappe, "clear_cache"):
			defaults.ensure_time_zone()
		return set_value.call_args

	def test_the_installers_zone_becomes_tehran(self):
		for stock in ("", None, "Asia/Kolkata"):
			self.assertEqual(self.run_with(stock).args, ("System Settings", "time_zone", "Asia/Tehran"))

	def test_a_zone_somebody_chose_is_left_alone(self):
		for chosen in ("Europe/London", "Asia/Dubai", "Asia/Tehran"):
			self.assertIsNone(self.run_with(chosen))
