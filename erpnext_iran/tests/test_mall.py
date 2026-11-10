import datetime
import unittest
from unittest.mock import patch

import frappe

from erpnext_iran import mall
from erpnext_iran.erpnext_iran.report.mall_arrears import mall_arrears
from erpnext_iran.erpnext_iran.report.mall_occupancy import mall_occupancy

D = datetime.date


def lease(**extra):
	base = {
		"name": "LEASE-1", "unit": "A1", "tenant": "T", "company": "Co", "area": 20, "monthly_rent": 10_000_000,
		"annual_increase_percent": 0, "service_charge_per_m2": 50_000, "turnover_percent": 0, "docstatus": 1,
		"start_date": D(2026, 3, 21), "end_date": D(2028, 3, 19), "terminated_on": None,
	}
	return frappe._dict({**base, **extra})


class TestJalaliMonths(unittest.TestCase):
	def test_month_lengths(self):
		for month in range(1, 7):
			self.assertEqual(mall.days_in_month(1405, month), 31)
		for month in range(7, 12):
			self.assertEqual(mall.days_in_month(1405, month), 30)
		self.assertEqual(mall.days_in_month(1403, 12), 30)  # a leap year
		self.assertEqual(mall.days_in_month(1404, 12), 29)

	def test_a_month_runs_from_its_first_day_to_the_day_before_the_next(self):
		self.assertEqual(mall.period_dates(1405, 1), (D(2026, 3, 21), D(2026, 4, 20)))
		for month in range(1, 12):
			_start, end = mall.period_dates(1405, month)
			self.assertEqual(mall.period_dates(1405, month + 1)[0], end + datetime.timedelta(days=1))
		self.assertEqual(mall.period_dates(1405, 12)[1] + datetime.timedelta(days=1), mall.period_dates(1406, 1)[0])

	def test_period_of_and_previous(self):
		self.assertEqual(mall.period_of(D(2026, 3, 21)), (1405, 1))
		self.assertEqual(mall.period_of(D(2026, 3, 20)), (1404, 12))
		self.assertEqual(mall.previous_period(1405, 1), (1404, 12))
		self.assertEqual(mall.previous_period(1405, 5), (1405, 4))

	def test_keys(self):
		self.assertEqual(mall.period_key(1405, 8), "1405-08")
		self.assertEqual(mall.period_key(1405, 8, "turnover"), "1405-08-T")


class TestCharges(unittest.TestCase):
	def test_a_whole_month(self):
		charge = mall.charges_for(lease(), 1405, 2)
		self.assertEqual((charge["rent"], charge["service"], charge["days"]), (10_000_000, 1_000_000, 31))

	def test_the_first_month_is_a_share_of_the_days(self):
		# starts on 16 Farvardin: 16 of 31 days
		charge = mall.charges_for(lease(start_date=D(2026, 4, 5)), 1405, 1)
		self.assertEqual(charge["days"], 16)
		self.assertEqual(charge["rent"], round(10_000_000 * 16 / 31))
		self.assertEqual(charge["service"], round(1_000_000 * 16 / 31))

	def test_nothing_before_the_start_or_after_the_end(self):
		self.assertEqual(mall.charges_for(lease(), 1404, 12)["rent"], 0)
		self.assertEqual(mall.charges_for(lease(end_date=D(2026, 5, 21)), 1405, 3)["rent"], 0)

	def test_the_last_month_is_a_share_too(self):
		charge = mall.charges_for(lease(end_date=D(2026, 4, 20) + datetime.timedelta(days=10)), 1405, 2)  # ends 10 days into Ordibehesht
		self.assertEqual(charge["days"], 10)
		self.assertEqual(charge["rent"], round(10_000_000 * 10 / 31))

	def test_the_rent_rises_on_every_anniversary_on_top_of_the_last_year(self):
		rising = lease(annual_increase_percent=10, end_date=D(2031, 1, 1))
		self.assertEqual(mall.charges_for(rising, 1405, 12)["rent"], 10_000_000)  # the last month of year one
		self.assertEqual(mall.charges_for(rising, 1406, 1)["rent"], 11_000_000)
		self.assertEqual(mall.charges_for(rising, 1406, 12)["rent"], 11_000_000)
		self.assertEqual(mall.charges_for(rising, 1407, 1)["rent"], 12_100_000)
		self.assertEqual(mall.years_in(rising, 1405, 1), 0)

	def test_the_service_charge_does_not_rise_with_the_rent(self):
		self.assertEqual(mall.charges_for(lease(annual_increase_percent=10, end_date=D(2031, 1, 1)), 1407, 1)["service"], 1_000_000)

	def test_termination_ends_the_charges_that_day(self):
		ended = lease(terminated_on=D(2026, 5, 1))  # 11 Ordibehesht: 11 days of 31
		self.assertEqual(mall.charges_for(ended, 1405, 2)["days"], 11)
		self.assertEqual(mall.charges_for(ended, 1405, 3)["rent"], 0)

	def test_a_lease_with_no_service_charge(self):
		self.assertEqual(mall.charges_for(lease(service_charge_per_m2=0), 1405, 2)["service"], 0)

	def test_the_last_month_of_a_leap_year_is_30_days(self):
		charge = mall.charges_for(lease(start_date=D(2024, 3, 20), end_date=D(2030, 1, 1)), 1403, 12)
		self.assertEqual((charge["days"], charge["days_in_month"]), (30, 30))


class TestTurnoverRent(unittest.TestCase):
	def test_only_what_the_share_is_above_the_base_rent_is_charged(self):
		with patch.object(mall.frappe.db, "get_value", return_value=200_000_000):
			result = mall.turnover_rent(lease(turnover_percent=8), 1405, 2)
		self.assertEqual((result["share"], result["base"], result["amount"]), (16_000_000, 10_000_000, 6_000_000))

	def test_a_share_below_the_base_rent_charges_nothing(self):
		with patch.object(mall.frappe.db, "get_value", return_value=50_000_000):
			self.assertEqual(mall.turnover_rent(lease(turnover_percent=8), 1405, 2)["amount"], 0)

	def test_no_percentage_or_no_figure_means_no_turnover_rent(self):
		with patch.object(mall.frappe.db, "get_value", return_value=10**9):
			self.assertIsNone(mall.turnover_rent(lease(turnover_percent=0), 1405, 2))
		with patch.object(mall.frappe.db, "get_value", return_value=None):
			self.assertIsNone(mall.turnover_rent(lease(turnover_percent=8), 1405, 2))


class TestStatus(unittest.TestCase):
	def test_status_follows_the_dates(self):
		contract = lease()
		self.assertEqual(mall.lease_status(contract, D(2026, 1, 1)), "Upcoming")
		self.assertEqual(mall.lease_status(contract, D(2027, 1, 1)), "Active")
		self.assertEqual(mall.lease_status(contract, D(2028, 3, 19)), "Active")
		self.assertEqual(mall.lease_status(contract, D(2028, 3, 20)), "Expired")

	def test_drafts_cancelled_and_terminated(self):
		self.assertEqual(mall.lease_status(lease(docstatus=0)), "Draft")
		self.assertEqual(mall.lease_status(lease(docstatus=2)), "Cancelled")
		self.assertEqual(mall.lease_status(lease(terminated_on=D(2026, 6, 1)), D(2026, 7, 1)), "Terminated")
		self.assertEqual(mall.lease_status(lease(terminated_on=D(2026, 6, 1)), D(2026, 5, 1)), "Active")


class TestValidate(unittest.TestCase):
	def run_validate(self, others=(), unit_status="Vacant", **fields):
		contract = lease(docstatus=0, name=None, **fields)
		contract.setdefault("invoice_day", None)
		with patch.object(mall.frappe.db, "get_value", return_value=frappe._dict(company="Co", status=unit_status)), patch.object(
			mall.frappe, "get_all", return_value=list(others)
		):
			mall.validate_lease(contract)
		return contract

	def refused(self, **kw):
		with self.assertRaises(frappe.ValidationError):
			self.run_validate(**kw)

	def test_a_good_lease_passes_and_is_a_draft(self):
		self.assertEqual(self.run_validate().status, "Draft")

	def test_dates_rent_and_percentages(self):
		self.refused(end_date=D(2026, 1, 1))
		self.refused(monthly_rent=0)
		self.refused(annual_increase_percent=101)
		self.refused(turnover_percent=-1)
		self.refused(invoice_day=29)
		self.refused(invoice_day=30)

	def test_a_unit_under_maintenance_cannot_be_let(self):
		self.refused(unit_status="Maintenance")

	def test_two_leases_cannot_overlap_on_a_unit(self):
		other = frappe._dict(name="LEASE-0", start_date=D(2027, 1, 1), end_date=D(2027, 12, 31), terminated_on=None)
		self.refused(others=[other])  # ours runs 2026-03 to 2028-03

	def test_a_lease_may_follow_another_and_may_take_over_a_terminated_one(self):
		after = frappe._dict(name="LEASE-0", start_date=D(2020, 1, 1), end_date=D(2026, 3, 20), terminated_on=None)
		self.run_validate(others=[after])
		cut_short = frappe._dict(name="LEASE-0", start_date=D(2026, 1, 1), end_date=D(2030, 1, 1), terminated_on=D(2026, 3, 1))
		self.run_validate(others=[cut_short])


class TestReports(unittest.TestCase):
	def test_arrears_age_in_steps_of_thirty_days(self):
		for days, name in ((-5, "Not Due"), (0, "Not Due"), (1, "1-30"), (30, "1-30"), (31, "31-60"), (60, "31-60"), (61, "61-90"), (90, "61-90"), (91, "90+")):
			self.assertEqual(mall_arrears.bucket(days), name, days)

	def test_occupancy_does_not_count_a_unit_under_maintenance_against_the_mall(self):
		rows = [frappe._dict(status="Leased", area=50), frappe._dict(status="Vacant", area=50), frappe._dict(status="Maintenance", area=100)]
		line = mall_occupancy.line("1", rows)
		self.assertEqual((line["units"], line["leased"], line["vacant"], line["maintenance"]), (3, 1, 1, 1))
		self.assertAlmostEqual(line["by_units"], 50)
		self.assertAlmostEqual(line["by_area"], 50)

	def test_an_empty_floor_is_zero_not_an_error(self):
		self.assertEqual(mall_occupancy.percent(0, 0), 0)
		self.assertEqual(mall_occupancy.line("x", [])["by_units"], 0)


class TestEndpoints(unittest.TestCase):
	def test_what_changes_data_is_post_only(self):
		for function in (mall.generate_invoices, mall.terminate_lease):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[function], ["POST"])

	def test_bad_months_are_refused(self):
		for month in (0, 13):
			with self.assertRaises(frappe.ValidationError):
				mall.bill_period(1405, month)
		with self.assertRaises(frappe.ValidationError):
			mall.bill_period(1405, 5, "bogus")
