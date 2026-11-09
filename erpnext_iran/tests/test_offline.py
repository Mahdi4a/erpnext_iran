import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import frappe

from erpnext_iran import offline


def sale(**extra):
	return {
		"id": "abcd1234-ef567890",
		"pos_profile": "P",
		"mode": "Cash",
		"sold_at": datetime.now().strftime(offline.TIME_FORMAT),
		"offline_total": 100000,
		"items": [{"item_code": "A", "qty": 1, "rate": 100000, "list_rate": 100000}],
		**extra,
	}


class TestCleanSale(unittest.TestCase):
	def test_a_good_sale_is_kept_as_sent(self):
		clean = offline.clean_sale(sale())
		self.assertEqual(clean["items"][0], {"item_code": "A", "qty": 1, "rate": 100000, "list_rate": 100000})
		self.assertEqual(clean["mode"], "Cash")

	def test_a_missing_list_rate_means_no_discount(self):
		clean = offline.clean_sale(sale(items=[{"item_code": "A", "qty": 2, "rate": 500}]))
		self.assertEqual(clean["items"][0]["list_rate"], 500)

	def test_a_mobile_is_normalised(self):
		self.assertEqual(offline.clean_sale(sale(mobile="+98 912 123 4567"))["mobile"], "09121234567")

	def test_bad_sales_are_refused(self):
		bad = [
			"not a sale",
			sale(id="short"),
			sale(id="has space in it!!"),
			sale(items=[]),
			sale(items="x"),
			sale(items=[{"item_code": "", "qty": 1, "rate": 1}]),
			sale(items=[{"item_code": "A", "qty": 0, "rate": 1}]),
			sale(items=[{"item_code": "A", "qty": -1, "rate": 1}]),
			sale(items=[{"item_code": "A", "qty": 1, "rate": -5}]),
			sale(items=["A"]),
			sale(sold_at="yesterday"),
			sale(sold_at="2099-01-01 10:00:00"),
			sale(mobile="0912"),
			sale(items=[{"item_code": "A", "qty": 1, "rate": 1}] * (offline.MAX_LINES + 1)),
		]
		for case in bad:
			with self.assertRaises(offline.RefusedSale, msg=str(case)[:60]):
				offline.clean_sale(case)


class TestSubmitOne(unittest.TestCase):
	def test_an_id_already_booked_is_a_duplicate_and_nothing_is_built(self):
		with patch.object(offline, "existing_invoice", return_value="SINV-1"), patch.object(offline, "build_invoice") as build:
			result = offline.submit_one(sale())
		self.assertEqual(result, {"id": "abcd1234-ef567890", "status": "duplicate", "invoice": "SINV-1"})
		build.assert_not_called()

	def test_a_refusal_comes_back_with_its_reason_and_rolls_back(self):
		doc = MagicMock()
		doc.insert.side_effect = frappe.ValidationError("<b>Discount</b> too high")
		with patch.object(offline, "existing_invoice", return_value=None), patch.object(offline, "build_invoice", return_value=doc), patch.object(
			offline, "negative_stock_allowed"
		), patch.object(offline.frappe, "db", MagicMock()) as db:
			result = offline.submit_one(sale())
		self.assertEqual(result["status"], "refused")
		self.assertEqual(result["reason"], "Discount too high")
		db.rollback.assert_called_once()

	def test_two_requests_racing_for_one_id_end_as_a_duplicate(self):
		doc = MagicMock()
		doc.insert.side_effect = frappe.UniqueValidationError("Duplicate")
		with patch.object(offline, "existing_invoice", side_effect=[None, "SINV-9"]), patch.object(offline, "build_invoice", return_value=doc), patch.object(
			offline, "negative_stock_allowed"
		), patch.object(offline.frappe, "db", MagicMock()):
			result = offline.submit_one(sale())
		self.assertEqual((result["status"], result["invoice"]), ("duplicate", "SINV-9"))

	def test_an_unexpected_error_is_not_swallowed_so_the_till_retries(self):
		doc = MagicMock()
		doc.insert.side_effect = RuntimeError("database went away")
		with patch.object(offline, "existing_invoice", return_value=None), patch.object(offline, "build_invoice", return_value=doc), patch.object(
			offline, "negative_stock_allowed"
		):
			with self.assertRaises(RuntimeError):
				offline.submit_one(sale())

	def test_a_total_that_differs_is_reported_but_the_sale_is_kept(self):
		doc = MagicMock(rounded_total=120000, grand_total=120000)
		doc.name = "SINV-2"
		with patch.object(offline, "existing_invoice", return_value=None), patch.object(offline, "build_invoice", return_value=doc), patch.object(
			offline, "negative_stock_allowed"
		), patch.object(offline.frappe, "db", MagicMock()):
			result = offline.submit_one(sale())
		self.assertEqual(result["status"], "ok")
		self.assertIn("warning", result)

	def test_too_many_sales_in_one_call_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			offline.submit_sales([sale()] * (offline.MAX_SALES_PER_CALL + 1))


class TestTaxRows(unittest.TestCase):
	def profile(self, template):
		return frappe._dict(taxes_and_charges=template)

	def test_no_template_means_no_tax_and_exact(self):
		self.assertEqual(offline.tax_rows(self.profile(None)), {"rows": [], "exact": True})

	def test_only_rows_on_net_total_can_be_worked_out(self):
		rows = [
			frappe._dict(charge_type="On Net Total", rate=10, included_in_print_rate=0),
			frappe._dict(charge_type="Actual", rate=0, included_in_print_rate=0),
		]
		with patch.object(offline.frappe, "get_cached_doc", return_value=frappe._dict(taxes=rows)):
			result = offline.tax_rows(self.profile("VAT"))
		self.assertEqual(result, {"rows": [{"rate": 10.0, "included": 0}], "exact": False})


class TestNegativeStockFlag(unittest.TestCase):
	def setUp(self):
		from erpnext.stock import stock_ledger

		self.stock_ledger = stock_ledger
		offline.install()

	def run_check(self, refuse=0):
		with patch.object(offline.frappe.db, "get_single_value", return_value=refuse), patch.object(
			self.stock_ledger.frappe, "get_cached_doc", return_value=frappe._dict(allow_negative_stock=0)
		), patch.object(self.stock_ledger.frappe, "get_cached_value", return_value=0):
			outside = self.stock_ledger.is_negative_stock_allowed(item_code="X")
			with offline.negative_stock_allowed():
				inside = self.stock_ledger.is_negative_stock_allowed(item_code="X")
			after = self.stock_ledger.is_negative_stock_allowed(item_code="X")
		return outside, inside, after

	def test_only_the_offline_call_may_go_negative_and_the_flag_is_cleared_after(self):
		self.assertEqual(self.run_check(), (False, True, False))

	def test_the_setting_that_refuses_negative_stock_wins(self):
		self.assertEqual(self.run_check(refuse=1), (False, False, False))

	def test_the_flag_is_cleared_even_when_the_sale_fails(self):
		with patch.object(offline.frappe.db, "get_single_value", return_value=0):
			with self.assertRaises(ValueError):
				with offline.negative_stock_allowed():
					raise ValueError
		self.assertFalse(frappe.flags.get(offline.FLAG))

	def test_install_is_idempotent(self):
		first = self.stock_ledger.is_negative_stock_allowed
		offline.install()
		self.assertIs(self.stock_ledger.is_negative_stock_allowed, first)


class TestListRate(unittest.TestCase):
	def test_the_server_price_beats_the_one_the_till_claims(self):
		line = {"rate": 1, "list_rate": 1}  # a till that sends the same cut price as "list price"
		self.assertEqual(offline.effective_list_rate(100000, line), 100000)

	def test_the_tills_list_price_is_used_only_when_the_server_has_none(self):
		self.assertEqual(offline.effective_list_rate(0, {"rate": 80, "list_rate": 100}), 100)

	def test_a_rate_above_the_list_price_is_no_discount(self):
		self.assertEqual(offline.effective_list_rate(100, {"rate": 120, "list_rate": 100}), 120)


class TestSnapshotPermissions(unittest.TestCase):
	def test_a_cashier_needs_only_what_a_cashier_has(self):
		"""Sales User can read Item and Customer but not Item Price: asking for more would lock every cashier out."""
		asked = []

		def has_permission(doctype, ptype="read", doc=None, throw=False, **kwargs):
			asked.append(doctype)
			return True

		with patch.object(offline.frappe, "has_permission", side_effect=has_permission), patch.object(
			offline.frappe, "get_cached_doc", side_effect=RuntimeError("stop after the permission checks")
		):
			with self.assertRaises(RuntimeError):
				offline.snapshot("P")
		self.assertEqual(asked, ["POS Profile", "Item", "Customer"])


class TestBatchSplit(unittest.TestCase):
	def split(self, qty, batches, has_batch=True):
		import datetime as dt

		rows = [{"batch_no": n, "qty": q, "expiry_date": dt.date(*d) if d else None} for n, q, d in batches]
		with patch.object(offline.frappe, "get_cached_value", return_value=1 if has_batch else 0), patch(
			"erpnext.stock.doctype.batch.batch.get_batch_qty", return_value=rows
		):
			return offline.batch_split("I", qty, "W", "2026-11-09 12:00:00")

	STOCK = [("EXPIRED", 10, (2026, 11, 7)), ("NEAR", 15, (2026, 11, 13)), ("FAR", 30, (2027, 1, 8))]

	def test_an_item_without_batches_is_one_plain_line(self):
		self.assertEqual(self.split(7, [], has_batch=False), [(None, 7)])

	def test_the_batch_that_expires_first_is_sold_first(self):
		self.assertEqual(self.split(5, self.STOCK), [("NEAR", 5)])

	def test_a_line_spans_batches_in_expiry_order(self):
		self.assertEqual(self.split(40, self.STOCK), [("NEAR", 15), ("FAR", 25)])

	def test_an_expired_batch_is_never_sold(self):
		self.assertNotIn("EXPIRED", [b for b, _q in self.split(45, self.STOCK)])

	def test_stock_that_only_expired_batches_hold_is_not_enough(self):
		with self.assertRaises(offline.RefusedSale):
			self.split(46, self.STOCK)  # 45 unexpired
		with self.assertRaises(offline.RefusedSale):
			self.split(1, [("EXPIRED", 10, (2026, 11, 7))])

	def test_a_batch_that_expires_today_can_still_be_sold_today(self):
		self.assertEqual(self.split(3, [("TODAY", 5, (2026, 11, 9))]), [("TODAY", 3)])

	def test_a_batch_without_an_expiry_date_comes_last(self):
		self.assertEqual(self.split(20, [("OPEN", 50, None), ("DATED", 15, (2026, 12, 1))]), [("DATED", 15), ("OPEN", 5)])

	def test_empty_and_zero_quantity_batches_are_skipped(self):
		self.assertEqual(self.split(2, [("EMPTY", 0, (2026, 11, 10)), ("OK", 5, (2026, 11, 20))]), [("OK", 2)])
