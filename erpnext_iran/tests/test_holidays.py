import datetime
import unittest

from erpnext_iran import holidays


class TestHolidays(unittest.TestCase):
	def setUp(self):
		self.year = dict(holidays.official_holidays(1405))

	def test_1405_has_the_22_holidays_that_are_not_on_a_friday(self):
		self.assertEqual(len(self.year), 22)
		self.assertTrue(all(date.strftime("%A") != "Friday" for date in self.year))

	def test_a_solar_and_a_lunar_occasion_on_one_day_are_written_once_with_both_names(self):
		self.assertEqual(self.year[datetime.date(2026, 3, 21)], "جشن نوروز و عید سعید فطر")
		self.assertEqual(self.year[datetime.date(2026, 6, 4)], "رحلت امام خمینی و عید سعید غدیر خم")

	def test_known_dates(self):
		self.assertEqual(self.year[datetime.date(2026, 6, 25)], "عاشورای حسینی")
		self.assertEqual(self.year[datetime.date(2027, 2, 11)], "پیروزی انقلاب اسلامی")

	def test_a_holiday_on_a_friday_is_left_to_the_weekly_off(self):
		self.assertNotIn(datetime.date(2026, 6, 5), self.year)  # 15 Khordad

	def test_a_year_without_lunar_dates_gets_no_list(self):
		self.assertIsNone(holidays.ensure_holiday_list(1406))
