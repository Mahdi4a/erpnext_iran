import unittest

from erpnext_iran import cities
from erpnext_iran.fields import PROVINCES


class TestCities(unittest.TestCase):
	def test_every_province_has_cities_in_alphabetical_order(self):
		for province in PROVINCES:
			with self.subTest(province):
				found = cities.get_cities(province)
				self.assertTrue(found)
				self.assertEqual(found, sorted(found))

	def test_the_capital_of_a_province_is_in_its_list(self):
		self.assertIn("رشت", cities.get_cities("گیلان"))
		self.assertIn("تهران", cities.get_cities("تهران"))
		self.assertIn("اراک", cities.get_cities("مرکزی"))

	def test_a_name_that_is_not_a_province_has_no_cities(self):
		self.assertEqual(cities.get_cities("Bavaria"), [])
		self.assertEqual(cities.get_cities(None), [])

	def test_the_arabic_letters_of_the_source_are_the_persian_ones(self):
		for found in cities.all_cities().values():
			for name in found:
				self.assertNotIn("ي", name)
				self.assertNotIn("ك", name)
