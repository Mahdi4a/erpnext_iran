import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from erpnext_iran import scale

SETTINGS = {"prefix": "2", "plu_digits": 6, "value_digits": 5, "mode": "Weight", "weight_divisor": 1000}


class TestScaleLabels(unittest.TestCase):
	def test_the_check_digit_matches_a_known_ean13(self):
		self.assertEqual(scale.ean13_check_digit("626000000001"), "9")
		self.assertEqual(scale.ean13_check_digit("400638133393"), "1")

	def test_an_item_barcode_is_the_prefix_the_plu_and_zeros(self):
		code = scale.item_barcode("000123", SETTINGS)
		self.assertEqual(code[:12], "200012300000")
		self.assertEqual(len(code), 13)
		self.assertEqual(code[12], scale.ean13_check_digit(code[:12]))

	def test_a_label_gives_the_item_barcode_and_the_weight(self):
		body = "2" + "000123" + "00350"
		label = body + scale.ean13_check_digit(body)
		parsed = scale.parse_label(label, SETTINGS)
		self.assertEqual(parsed, {"barcode": scale.item_barcode("000123", SETTINGS), "value": 350})

	def test_codes_that_are_not_scale_labels_are_left_alone(self):
		body = "2" + "000123" + "00350"
		good = body + scale.ean13_check_digit(body)
		wrong_check = body + str((int(good[12]) + 1) % 10)
		for code in ("6260000000019", wrong_check, "2000123", "abc", ""):
			with self.subTest(code):
				self.assertIsNone(scale.parse_label(code, SETTINGS))

	def test_digits_that_do_not_add_up_to_twelve_are_refused(self):
		with patch.object(scale.frappe, "throw", side_effect=Exception("bad")):
			with self.assertRaises(Exception):
				scale.item_barcode("123", SETTINGS)


class TestItemValidation(unittest.TestCase):
	def run_it(self, plu, barcodes=None, before_plu=None, other=None):
		doc = MagicMock()
		doc.name = "Apple"
		doc.get.side_effect = lambda key, default=None: plu if key == "scale_plu" else default
		doc.barcodes = list(barcodes or [])
		doc.get_doc_before_save.return_value = SimpleNamespace(get=lambda k, d=None: before_plu) if before_plu is not None else None
		with (
			patch.object(scale, "get_scale_settings", return_value=SETTINGS),
			patch.object(scale.frappe, "db", MagicMock()) as db,
			patch.object(scale.frappe, "throw", side_effect=Exception("refused")),
		):
			db.get_value.return_value = other
			scale.validate_item(doc)
		return doc

	def test_an_item_with_a_plu_gets_its_barcode_once(self):
		doc = self.run_it("000123")
		doc.append.assert_called_once_with(
			"barcodes", {"barcode": scale.item_barcode("000123", SETTINGS), "barcode_type": "EAN"}
		)

	def test_the_barcode_is_not_added_again(self):
		row = SimpleNamespace(barcode=scale.item_barcode("000123", SETTINGS))
		self.run_it("000123", barcodes=[row]).append.assert_not_called()

	def test_a_plu_of_the_wrong_length_or_one_in_use_is_refused(self):
		with self.assertRaises(Exception):
			self.run_it("123")
		with self.assertRaises(Exception):
			self.run_it("000123", other="Pear")

	def test_changing_the_plu_removes_the_old_barcode(self):
		old = SimpleNamespace(barcode=scale.item_barcode("000111", SETTINGS))
		doc = self.run_it("000123", barcodes=[old], before_plu="000111")
		self.assertEqual(doc.barcodes, [])

	def test_an_item_without_a_plu_is_left_alone(self):
		self.run_it("").append.assert_not_called()


class TestBootRegistry(unittest.TestCase):
	def test_only_items_with_a_plu_of_the_right_length_are_listed_as_barcodes(self):
		boot = SimpleNamespace(erpnext_iran={})
		with (
			patch.object(scale, "get_scale_settings", return_value=dict(SETTINGS)),
			patch.object(scale, "registered_barcodes", return_value=["000123", "12"]) if False else patch.object(scale.frappe, "get_all", return_value=["000123", "12", "000123"]),
		):
			scale.extend_bootinfo(boot)
		self.assertEqual(boot.erpnext_iran["scale"]["items"], [scale.item_barcode("000123", SETTINGS)])
