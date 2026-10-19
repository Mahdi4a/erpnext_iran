import datetime
import unittest
from unittest.mock import patch

from erpnext_iran import jalali


class TestJalali(unittest.TestCase):
	def test_fiscal_year_starts_on_1_farvardin(self):
		start, end = jalali.fiscal_year_dates(1404)

		self.assertEqual(start, datetime.date(2025, 3, 21))
		self.assertEqual(end, datetime.date(2026, 3, 20))

	def test_a_leap_year_ends_on_30_esfand(self):
		# 1403 is a leap year: 366 days, ending on 30 Esfand 1403 (2025-03-20)
		start, end = jalali.fiscal_year_dates(1403)

		self.assertEqual(start, datetime.date(2024, 3, 20))
		self.assertEqual(end, datetime.date(2025, 3, 20))
		self.assertEqual((end - start).days + 1, 366)

	def test_consecutive_fiscal_years_have_no_gap_and_no_overlap(self):
		for year in range(1400, 1420):
			_, end = jalali.fiscal_year_dates(year)
			next_start, _ = jalali.fiscal_year_dates(year + 1)
			self.assertEqual(end + datetime.timedelta(days=1), next_start)

	def test_current_jalali_year_flips_on_nowruz(self):
		self.assertEqual(jalali.current_jalali_year(datetime.date(2025, 3, 20)), 1403)
		self.assertEqual(jalali.current_jalali_year(datetime.date(2025, 3, 21)), 1404)

	def test_jalali_date_filter(self):
		with patch.object(jalali, "persian_digits_enabled", return_value=False):
			self.assertEqual(jalali.jalali_date("2025-03-21"), "1404-01-01")
			self.assertEqual(jalali.jalali_date(datetime.date(2025, 3, 21), True), "1 فروردین 1404")
			self.assertEqual(jalali.jalali_date(None), "")
		with patch.object(jalali, "persian_digits_enabled", return_value=True):
			self.assertEqual(jalali.jalali_date("2025-03-21"), "۱۴۰۴-۰۱-۰۱")

	def test_years_that_are_not_exactly_one_gregorian_year_need_the_short_year_flag(self):
		self.assertTrue(jalali.needs_no_exception(*jalali.fiscal_year_dates(1404)))
		# 1403 has 366 days from 2024-03-20, which ends a day after ERPNext's expectation
		self.assertFalse(jalali.needs_no_exception(*jalali.fiscal_year_dates(1403)))
