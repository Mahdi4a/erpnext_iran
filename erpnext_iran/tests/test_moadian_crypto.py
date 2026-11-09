from __future__ import annotations

import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID

from erpnext_iran.moadian_crypto import (
	decode_base64url,
	encrypt_jwe,
	load_server_public_key,
	sign_jws,
)


def make_certificate(private_key) -> x509.Certificate:
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "moadian-test")])
	now = datetime.now(timezone.utc)
	return (
		x509.CertificateBuilder()
		.subject_name(name)
		.issuer_name(name)
		.public_key(private_key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now)
		.not_valid_after(now + timedelta(days=1))
		.sign(private_key, hashes.SHA256())
	)


class TestMoadianCrypto(unittest.TestCase):
	def setUp(self):
		self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		self.certificate = make_certificate(self.private_key)

	def test_signed_jws_verifies_with_the_certificate_and_carries_the_signing_time(self):
		token = sign_jws({"nonce": "n1", "clientId": "A11216"}, self.private_key, self.certificate, "2024-03-06T13:05:50Z")
		header, payload, signature = token.split(".")
		self.certificate.public_key().verify(
			decode_base64url(signature), f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256()
		)
		self.assertEqual(json.loads(decode_base64url(payload)), {"nonce": "n1", "clientId": "A11216"})
		decoded_header = json.loads(decode_base64url(header))
		self.assertEqual(
			(decoded_header["alg"], decoded_header["sigT"], decoded_header["crit"]),
			("RS256", "2024-03-06T13:05:50Z", ["sigT"]),
		)
		self.assertEqual((decoded_header["typ"], decoded_header["cty"]), ("jose", "text/plain"))

	def test_jwe_opens_with_the_server_private_key_and_returns_the_signed_invoice(self):
		server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		der = server_key.public_key().public_bytes(
			serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
		)
		token = encrypt_jwe("signed.invoice.jws", load_server_public_key(base64.b64encode(der).decode()), "kid-1")
		header, encrypted_key, iv, ciphertext, tag = token.split(".")
		content_key = server_key.decrypt(
			decode_base64url(encrypted_key),
			padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
		)
		opened = AESGCM(content_key).decrypt(
			decode_base64url(iv), decode_base64url(ciphertext) + decode_base64url(tag), header.encode()
		)
		self.assertEqual(opened, b"signed.invoice.jws")
		self.assertEqual(json.loads(decode_base64url(header))["kid"], "kid-1")
