import base64
import hashlib
import hmac
import unittest
from unittest.mock import MagicMock, patch

import frappe

from erpnext_iran import channels, woocommerce

CONFIG = frappe._dict(
	woo_company="Co", woo_warehouse="WH", woo_price_list="PL", woo_price_factor=1, woo_shipping_account=None, woo_run_as=None
)


def order(**extra):
	base = {
		"id": 501, "number": "501", "status": "processing", "currency": "IRR", "total": "300000", "shipping_total": "20000",
		"billing": {"first_name": "A", "last_name": "B", "phone": "09121112233"},
		"shipping": {"address_1": "Valiasr 1", "city": "Tehran"},
		"line_items": [{"sku": "TST-RET-1", "quantity": 2, "total": "200000", "product_id": 9}],
	}
	base.update(extra)
	return base


class TestSignature(unittest.TestCase):
	def sign(self, body, secret):
		return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

	def test_a_good_signature_passes(self):
		body = b'{"id": 1}'
		self.assertTrue(woocommerce.signature_ok(body, self.sign(body, "s3"), "s3"))

	def test_wrong_secret_changed_body_or_missing_pieces_fail(self):
		body = b'{"id": 1}'
		self.assertFalse(woocommerce.signature_ok(body, self.sign(body, "other"), "s3"))
		self.assertFalse(woocommerce.signature_ok(b'{"id": 2}', self.sign(body, "s3"), "s3"))
		self.assertFalse(woocommerce.signature_ok(body, None, "s3"))
		self.assertFalse(woocommerce.signature_ok(body, self.sign(body, "s3"), None))
		self.assertFalse(woocommerce.signature_ok(body, "", ""))


class TestOrders(unittest.TestCase):
	def test_a_paid_order_is_created_once(self):
		with patch.object(woocommerce, "existing_order", return_value=None), patch.object(
			woocommerce, "item_for", return_value="TST-RET-1"
		), patch.object(woocommerce, "customer_for", return_value="0912"), patch.object(
			woocommerce.frappe, "new_doc"
		) as new_doc:
			doc = MagicMock()
			doc.name = "SO-1"
			new_doc.return_value = doc
			result = woocommerce.create_sales_order(order(), CONFIG)
		self.assertEqual(result, {"status": "created", "order": "SO-1"})
		doc.submit.assert_called_once()
		item_rows = [call.args[1] for call in doc.append.call_args_list if call.args[0] == "items"]
		self.assertEqual(item_rows, [{"item_code": "TST-RET-1", "qty": 2.0, "rate": 100000.0, "warehouse": "WH"}])

	def test_the_same_order_twice_is_a_duplicate(self):
		with patch.object(woocommerce, "existing_order", return_value="SO-1"):
			self.assertEqual(woocommerce.create_sales_order(order(), CONFIG), {"status": "duplicate", "order": "SO-1"})

	def test_an_unknown_sku_is_refused_with_a_todo_not_an_error(self):
		with patch.object(woocommerce, "existing_order", return_value=None), patch.object(
			woocommerce, "item_for", return_value=None
		), patch.object(woocommerce, "refuse", return_value={"status": "refused"}) as refuse:
			result = woocommerce.create_sales_order(order(), CONFIG)
		self.assertEqual(result["status"], "refused")
		self.assertIn("TST-RET-1", refuse.call_args.args[1])

	def test_a_foreign_currency_is_refused(self):
		with patch.object(woocommerce, "existing_order", return_value=None), patch.object(
			woocommerce, "refuse", return_value={"status": "refused"}
		) as refuse:
			woocommerce.create_sales_order(order(currency="USD"), CONFIG)
		refuse.assert_called_once()

	def test_the_price_factor_turns_tomans_into_rials(self):
		config = frappe._dict(CONFIG, woo_price_factor=10)
		with patch.object(woocommerce, "existing_order", return_value=None), patch.object(
			woocommerce, "item_for", return_value="X"
		), patch.object(woocommerce, "customer_for", return_value="C"), patch.object(woocommerce.frappe, "new_doc") as new_doc:
			doc = MagicMock()
			new_doc.return_value = doc
			woocommerce.create_sales_order(order(currency="IRT"), config)
		rows = [call.args[1] for call in doc.append.call_args_list if call.args[0] == "items"]
		self.assertEqual(rows[0]["rate"], 1000000.0)

	def test_statuses(self):
		lock = MagicMock()
		with patch("frappe.utils.synchronization.filelock", return_value=lock), patch.object(
			woocommerce, "create_sales_order", return_value={"status": "created"}
		) as create, patch.object(woocommerce, "cancel_sales_order", return_value={"status": "cancelled"}) as cancel:
			self.assertEqual(woocommerce.handle_order(order(status="completed"), CONFIG)["status"], "created")
			self.assertEqual(woocommerce.handle_order(order(status="cancelled"), CONFIG)["status"], "cancelled")
			self.assertEqual(woocommerce.handle_order(order(status="pending"), CONFIG)["status"], "ignored")
			self.assertEqual(woocommerce.handle_order(order(status="on-hold"), CONFIG)["status"], "ignored")
		create.assert_called_once()
		cancel.assert_called_once()

	def test_address_text_prefers_the_shipping_address(self):
		text = woocommerce.address_text(order())
		self.assertIn("Valiasr 1", text)
		self.assertIn("Tehran", text)


class TestPush(unittest.TestCase):
	def test_money_converts_by_the_factor(self):
		self.assertEqual(woocommerce.money(100000, frappe._dict(woo_price_factor=1)), "100000")
		self.assertEqual(woocommerce.money(100000, frappe._dict(woo_price_factor=10)), "10000")
		self.assertEqual(woocommerce.money(105, frappe._dict(woo_price_factor=10)), "10.50")

	def test_known_products_go_in_one_batch_and_new_ones_are_created(self):
		config = frappe._dict(CONFIG, woo_enabled=1)
		items = [
			frappe._dict(name="A", item_name="A", description="", image="", woo_product_id="11"),
			frappe._dict(name="B", item_name="B", description="", image="", woo_product_id=""),
		]
		calls = []

		def client(cfg, method, path, **kwargs):
			calls.append((method, path))
			if method == "GET":
				return []
			return {"id": 77}

		with patch.object(woocommerce, "settings", return_value=config), patch.object(
			woocommerce.frappe, "get_all", return_value=items
		), patch.object(woocommerce, "_client", side_effect=client), patch.object(
			woocommerce, "stock_payload", return_value={"regular_price": "1"}
		), patch.object(woocommerce.frappe.db, "set_value") as set_value, patch.object(
			woocommerce.frappe.db, "set_single_value"
		):
			result = woocommerce.push_items(None)
		self.assertEqual(result["updated"], 1)
		self.assertEqual(result["created"], 1)
		self.assertIn(("POST", "products/batch"), calls)
		self.assertIn(("POST", "products"), calls)
		set_value.assert_called_once()

	def test_a_store_error_is_collected_not_raised(self):
		config = frappe._dict(CONFIG, woo_enabled=1)
		items = [frappe._dict(name="A", item_name="A", description="", image="", woo_product_id="11")]
		with patch.object(woocommerce, "settings", return_value=config), patch.object(
			woocommerce.frappe, "get_all", return_value=items
		), patch.object(woocommerce, "_client", side_effect=woocommerce.WooError("500")), patch.object(
			woocommerce, "stock_payload", return_value={}
		), patch.object(woocommerce.frappe.db, "set_single_value"), patch.object(woocommerce.frappe, "log_error"):
			result = woocommerce.push_items(None)
		self.assertEqual(result["errors"], ["500"])

	def test_disabled_does_nothing(self):
		with patch.object(woocommerce, "settings", return_value=frappe._dict(woo_enabled=0)):
			self.assertEqual(woocommerce.push_items(None), {"updated": 0, "created": 0, "errors": []})


class TestCatalog(unittest.TestCase):
	def test_csv_has_the_meta_columns_and_skips_unpriced_items(self):
		items = [
			frappe._dict(name="A", item_name="Apple", description="<b>Red</b>", image="/files/a.png", brand="B", woo_product_id="5"),
			frappe._dict(name="NOPRICE", item_name="x", description="", image="", brand="", woo_product_id=""),
		]
		config = frappe._dict(shop_url="https://shop.example.ir/", catalog_price_list="PL", catalog_warehouse="")
		with patch.object(channels.frappe, "get_all", return_value=items), patch.object(
			channels, "price_of", side_effect=lambda code, pl: 50000 if code == "A" else 0
		), patch.object(channels, "stock_of", return_value=3):
			rows = channels.catalog_rows(config)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["price"], "50000 IRR")
		self.assertEqual(rows[0]["availability"], "in stock")
		self.assertEqual(rows[0]["link"], "https://shop.example.ir/?p=5")
		self.assertEqual(rows[0]["description"], "Red")
		text = channels.catalog_csv(rows)
		self.assertTrue(text.splitlines()[0].startswith("id,title,description,availability"))

	def test_the_feed_needs_the_token(self):
		fake = MagicMock()
		fake.get_password.return_value = "right"
		with patch.object(channels, "settings", return_value=fake):
			self.assertTrue(channels.token_ok("right"))
			self.assertFalse(channels.token_ok("wrong"))
			self.assertFalse(channels.token_ok(None))
			self.assertFalse(channels.token_ok(""))

	def test_a_till_sale_is_a_store_sale(self):
		doc = frappe._dict(is_pos=1, sales_channel="")
		channels.default_channel(doc)
		self.assertEqual(doc.sales_channel, "Store")
		other = frappe._dict(is_pos=0, sales_channel="")
		channels.default_channel(other)
		self.assertEqual(other.sales_channel, "")
