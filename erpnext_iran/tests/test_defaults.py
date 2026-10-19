import unittest
from unittest.mock import patch

from erpnext_iran import defaults


class FakeDoc(dict):
	def set(self, key, value):
		self[key] = value


class FakeSettings(FakeDoc):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.flags = type("Flags", (), {})()
		self.saved = False

	def save(self):
		self.saved = True


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
		settings = FakeSettings(
			number_format="#,###.##",
			currency_precision="2",
			first_day_of_the_week="Monday",
			time_zone="Europe/Berlin",
		)
		with patch.object(defaults.frappe, "get_single", return_value=settings):
			defaults.apply_system_defaults()

		self.assertTrue(settings.saved)
		self.assertEqual(settings["number_format"], "#,###")
		self.assertEqual(settings["currency_precision"], "0")
		self.assertEqual(settings["first_day_of_the_week"], "Saturday")
		self.assertEqual(settings["time_zone"], "Europe/Berlin")
