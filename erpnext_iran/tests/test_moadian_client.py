import base64
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from erpnext_iran import moadian_client, moadian_taxid
from erpnext_iran.moadian_client import MoadianClient, pem_from_text, tehran_time
from erpnext_iran.moadian_send import error_text
from erpnext_iran.tests.test_moadian_crypto import make_certificate


class TestMoadianHelpers(unittest.TestCase):
	def test_pem_rebuilt_from_a_pasted_line_has_headers_and_64_character_lines(self):
		pem = pem_from_text("-----BEGIN CERTIFICATE----- " + "A" * 100 + " -----END CERTIFICATE-----", "CERTIFICATE")
		lines = pem.strip().split("\n")
		self.assertEqual(lines[0], "-----BEGIN CERTIFICATE-----")
		self.assertEqual([len(line) for line in lines[1:-1]], [64, 36])

	def test_inquiry_time_is_written_with_the_tehran_offset_the_api_wants(self):
		moment = datetime(2023, 5, 14, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))
		self.assertEqual(tehran_time(moment), "2023-05-14T00:00:00.000000000+03:30")

	def test_errors_of_a_failed_inquiry_become_one_line_each(self):
		result = {"data": {"error": [{"code": "012802", "message": "bad"}, {"code": "011107", "message": "long"}]}}
		self.assertEqual(error_text(result), "012802: bad\n011107: long")

	def test_tax_id_matches_the_six_samples_of_the_official_documents(self):
		samples = [
			"A111220E1B9155CB1F18C7", "A1112K04D1271489087018", "A111DW04E8300003CC4EA5",
			"A111DW04E8300004349008", "A111H104EA6001D0B32AC6", "A1121604C220002F095011",
		]
		for sample in samples:
			days, serial = int(sample[6:11], 16), int(sample[11:21], 16)
			millis = (days * 86400 + 3600) * 1000
			self.assertEqual(moadian_taxid.tax_id(sample[:6], millis, serial), sample)

	def test_tax_id_day_comes_from_utc_seconds_so_an_invoice_just_after_midnight_in_tehran_keeps_the_utc_day(self):
		# 2025-03-21 00:30 Tehran is 2025-03-20 21:00 UTC: day 20167
		millis = 1742504400000
		self.assertTrue(moadian_taxid.tax_id("A11216", millis, 1).startswith("A1121604EC7"))


class TestMoadianClient(unittest.TestCase):
	def setUp(self):
		key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		self.server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		der = self.server_key.public_key().public_bytes(
			serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
		)
		self.server_info = {"publicKeys": [{"key": base64.b64encode(der).decode(), "id": "kid-1"}]}
		client = MoadianClient.__new__(MoadianClient)
		client.memory_id, client.base_url = "A11216", moadian_client.LIVE_URL
		client.private_key, client.certificate = key, make_certificate(key)
		self.client = client

	def fake_get(self, url, params=None, headers=None, timeout=None):
		answers = {"nonce": {"nonce": "n-1"}, "server-information": self.server_info}
		response = MagicMock()
		response.json.return_value = answers[url.rsplit("/", 1)[1]]
		return response

	def test_send_posts_one_encrypted_packet_and_returns_the_reference_number(self):
		post = MagicMock()
		post.return_value.json.return_value = {"result": [{"referenceNumber": "ref-1"}]}
		with patch.object(moadian_client.requests, "get", self.fake_get), patch.object(
			moadian_client.requests, "post", post
		):
			request_id, reference = self.client.send({"header": {"taxid": "x"}, "body": [], "payments": []})

		packet = post.call_args.kwargs["json"][0]
		self.assertEqual(reference, "ref-1")
		self.assertEqual(packet["header"], {"requestTraceId": request_id, "fiscalId": "A11216"})
		self.assertEqual(len(packet["payload"].split(".")), 5)
		self.assertTrue(post.call_args.kwargs["headers"]["Authorization"].startswith("Bearer "))


class TestMoadianCancellation(unittest.TestCase):
	def test_cancellation_names_the_cancelled_invoice_and_carries_no_items(self):
		from erpnext_iran import moadian_send

		original = {"header": {"inty": 1, "inp": 3, "tins": "411111111111"}}
		doc = MagicMock(moadian_tax_id="A1121604C220002F095011")
		doc.name = "SINV-1"
		with patch.object(moadian_send.moadian, "get_payload", return_value={"payload": original}), patch.object(
			moadian_send, "now_datetime", return_value=datetime(2025, 3, 21, 10, 30)
		):
			payload = moadian_send.cancellation_payload(doc, 7)

		self.assertEqual(
			(payload["header"]["ins"], payload["header"]["irtaxid"], payload["header"]["inno"], payload["header"]["inp"]),
			(3, "A1121604C220002F095011", "7", 3),
		)
		self.assertEqual((payload["body"], payload["payments"]), ([], []))


class TestMoadianAutoSend(unittest.TestCase):
	def test_gold_layout_shows_wage_profit_and_carat_but_not_the_flight_type(self):
		from erpnext_iran import moadian

		layout = moadian.pattern_layout()["3"]
		self.assertTrue({"consfee", "spro", "bros", "cui"} <= set(layout["item"]))
		self.assertNotIn("ft", layout["header"])

	def test_submit_sends_in_the_background_only_for_a_company_that_asked_for_it(self):
		from erpnext_iran import moadian_send

		doc = MagicMock(moadian_enabled=1, company="C")
		doc.name = "SINV-1"
		doc.get.side_effect = lambda key: getattr(doc, key)
		for asked, calls in ((1, 1), (0, 0)):
			with patch.object(moadian_send.frappe, "get_cached_value", return_value=asked), patch.object(
				moadian_send.frappe, "enqueue"
			) as enqueue:
				moadian_send.auto_send_on_submit(doc)
			self.assertEqual(enqueue.call_count, calls)

	def test_a_failed_automatic_send_keeps_the_reason_on_the_invoice(self):
		from erpnext_iran import moadian_send

		with patch.object(moadian_send, "send_invoice", side_effect=ValueError("control digit")), patch.object(
			moadian_send, "frappe"
		) as fake_frappe:
			moadian_send.auto_send("SINV-1")
		fake_frappe.db.set_value.assert_called_once_with("Sales Invoice", "SINV-1", "moadian_errors", "control digit")
