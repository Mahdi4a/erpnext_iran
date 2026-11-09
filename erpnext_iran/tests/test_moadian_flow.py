"""The client against the local Moadian stand-in: real keys, real signing, real encryption."""

import datetime
import unittest

import frappe
import requests
from cryptography.hazmat.primitives.asymmetric import rsa

from erpnext_iran import moadian
from erpnext_iran.moadian_client import MoadianClient
from erpnext_iran.moadian_taxid import tax_id
from erpnext_iran.tests.moadian_mock import MockMoadian
from erpnext_iran.tests.test_moadian import BUYER, ITEMS, SELLER, UNITS, pattern_invoice
from erpnext_iran.tests.test_moadian_crypto import make_certificate

MEMORY_ID = "A11216"


class TestMoadianFlow(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.mock = MockMoadian(MEMORY_ID)
		cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		cls.client = MoadianClient.__new__(MoadianClient)
		cls.client.memory_id, cls.client.base_url = MEMORY_ID, cls.mock.url
		cls.client.private_key, cls.client.certificate = cls.key, make_certificate(cls.key)

	@classmethod
	def tearDownClass(cls):
		cls.mock.stop()

	def send(self, invoice, serial=1, client=None):
		invoice.moadian_serial = serial
		payload = moadian.build_payload(invoice, SELLER, BUYER, ITEMS, UNITS)
		payload.pop("unverified")
		payload["header"]["taxid"] = tax_id(MEMORY_ID, payload["header"]["indatim"], serial)
		_, reference = (client or self.client).send(payload)
		return self.client.inquire(reference, datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1))

	def test_a_plain_sale_is_accepted_after_signature_encryption_and_tax_id_checks(self):
		result = self.send(pattern_invoice(1), serial=1)
		self.assertEqual((result["status"], result["data"]["error"]), ("SUCCESS", []))

	def test_the_server_received_exactly_the_invoice_the_client_built(self):
		self.send(pattern_invoice(1), serial=2)
		received = list(self.mock.invoices.values())[-1]
		self.assertEqual((received["header"]["inno"], received["header"]["tins"]), ("2", "411111111111"))
		self.assertEqual(received["body"][0]["sstid"], "2720000114257")

	def test_a_gold_invoice_without_wage_profit_and_commission_is_rejected_naming_them(self):
		result = self.send(pattern_invoice(3), serial=3)
		self.assertEqual(result["status"], "FAILED")
		text = " ".join(error["message"] for error in result["data"]["error"])
		for code in ("consfee", "spro", "bros", "tcpbs"):
			self.assertIn(f"Field {code} is mandatory", text)

	def test_a_gold_invoice_with_everything_filled_is_accepted(self):
		row = {"moadian_consfee": 10, "moadian_spro": 20, "moadian_bros": 5, "moadian_tcpbs": 35}
		self.assertEqual(self.send(pattern_invoice(3, row=row), serial=4)["status"], "SUCCESS")

	def test_a_wrong_control_digit_is_rejected_as_a_wrong_tax_id(self):
		invoice = pattern_invoice(1)
		invoice.moadian_serial = 5
		payload = moadian.build_payload(invoice, SELLER, BUYER, ITEMS, UNITS)
		payload.pop("unverified")
		good = tax_id(MEMORY_ID, payload["header"]["indatim"], 5)
		payload["header"]["taxid"] = good[:-1] + str((int(good[-1]) + 1) % 10)
		_, reference = self.client.send(payload)
		result = self.client.inquire(reference, datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1))
		self.assertEqual(result["data"]["error"][0]["message"], "Tax ID is wrong")

	def test_a_token_signed_with_another_memory_id_is_refused_with_401(self):
		other = MoadianClient.__new__(MoadianClient)
		other.memory_id, other.base_url = "B22222", self.mock.url
		other.private_key, other.certificate = self.key, self.client.certificate
		with self.assertRaises(requests.HTTPError) as caught:
			other.server_key()
		self.assertEqual(caught.exception.response.status_code, 401)

	def test_a_reused_nonce_is_refused(self):
		nonce = requests.get(f"{self.mock.url}/nonce").json()["nonce"]
		from erpnext_iran import moadian_crypto as crypto

		token = crypto.sign_jws({"nonce": nonce, "clientId": MEMORY_ID}, self.key, self.client.certificate)
		headers = {"Authorization": f"Bearer {token}"}
		self.assertEqual(requests.get(f"{self.mock.url}/server-information", headers=headers).status_code, 200)
		self.assertEqual(requests.get(f"{self.mock.url}/server-information", headers=headers).status_code, 401)

	def test_a_return_without_the_original_tax_id_is_rejected(self):
		invoice = pattern_invoice(1, is_return=1)
		self.assertEqual(self.send(invoice, serial=6)["status"], "FAILED")

	def test_a_return_that_points_at_the_original_is_accepted(self):
		original = tax_id(MEMORY_ID, 1742504400000, 7)
		invoice = pattern_invoice(1, is_return=1, moadian_reference_tax_id=original)
		self.assertEqual(self.send(invoice, serial=8)["status"], "SUCCESS")

	def test_a_cash_and_credit_sale_is_accepted_when_the_two_amounts_add_up_to_the_net_bill(self):
		invoice = pattern_invoice(1, moadian_settlement_method="3 - Cash and credit", paid_amount=500000)
		self.assertEqual(self.send(invoice, serial=9)["status"], "SUCCESS")
