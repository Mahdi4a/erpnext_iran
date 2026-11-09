"""A local stand-in for the Moadian collection API, strict where the real one is strict:
it checks the identity token (signature, one-use nonce, memory ID), opens the JWE with its own
private key, checks the invoice signature, the tax ID and the mandatory fields of the pattern.
It proves the client speaks the protocol; it is not the tax authority."""

from __future__ import annotations

import base64
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from erpnext_iran import moadian, moadian_taxid
from erpnext_iran.moadian_crypto import decode_base64url


class MockMoadian:
	def __init__(self, memory_id: str):
		self.memory_id = memory_id
		self.server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		self.key_id = str(uuid.uuid4())
		self.nonces, self.results, self.invoices = set(), {}, {}
		self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
		self.url = f"http://127.0.0.1:{self.httpd.server_port}"
		threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

	def stop(self):
		self.httpd.shutdown()
		self.httpd.server_close()

	# -- checks ---------------------------------------------------------------------------------
	def open_jws(self, token: str) -> dict:
		header_text, payload_text, signature = token.split(".")
		header = json.loads(decode_base64url(header_text))
		certificate = x509.load_der_x509_certificate(base64.b64decode(header["x5c"][0]))
		certificate.public_key().verify(
			decode_base64url(signature), f"{header_text}.{payload_text}".encode(), padding.PKCS1v15(), hashes.SHA256()
		)
		assert header["alg"] == "RS256" and "sigT" in header and header["crit"] == ["sigT"], "bad JWS header"
		return json.loads(decode_base64url(payload_text))

	def check_token(self, authorization: str):
		claims = self.open_jws(authorization.removeprefix("Bearer "))
		assert claims["nonce"] in self.nonces, "nonce unknown or already used"
		self.nonces.discard(claims["nonce"])
		assert claims["clientId"] == self.memory_id, "client ID is not this memory ID"

	def open_jwe(self, token: str) -> str:
		header_text, key, iv, ciphertext, tag = token.split(".")
		header = json.loads(decode_base64url(header_text))
		assert (header["alg"], header["enc"], header["kid"]) == ("RSA-OAEP-256", "A256GCM", self.key_id)
		oaep = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
		content_key = self.server_key.decrypt(decode_base64url(key), oaep)
		sealed = decode_base64url(ciphertext) + decode_base64url(tag)
		return AESGCM(content_key).decrypt(decode_base64url(iv), sealed, header_text.encode()).decode()

	def judge(self, invoice: dict) -> list[dict]:
		"""The errors of an invoice: tax ID, number, and the mandatory fields of its pattern."""
		header, errors = invoice["header"], []
		taxid = header.get("taxid", "")
		try:
			days, serial = int(taxid[6:11], 16), int(taxid[11:21], 16)
			good = taxid[:6] == self.memory_id and taxid[21] == moadian_taxid.control_digit(self.memory_id, days, serial)
			good = good and header["inno"] == str(serial) and days == header["indatim"] // 86_400_000
		except (ValueError, IndexError, KeyError):
			good = False
		if not good:
			errors.append({"code": "010101", "message": "Tax ID is wrong", "errorType": "ERROR"})
		if header.get("ins") == 3:  # a cancellation names the invoice and carries no items (v7.9 5-3)
			return errors + ([] if header.get("irtaxid") else [{"code": "010404", "message": "irtaxid is mandatory", "errorType": "ERROR"}])
		try:
			errors += [
				{"code": "010202", "message": f"Field {code} is mandatory", "errorType": "ERROR"}
				for code in moadian.pattern_gaps(invoice)
			]
		except ValueError as error:
			errors.append({"code": "010303", "message": str(error), "errorType": "ERROR"})
		if header.get("setm") == 3:
			net = header["tbill"] - header["tvam"] - header["todam"]
			cap, insp = header.get("cap", 0), header.get("insp", 0)
			if not (0 < cap < net and 0 < insp < net and cap + insp == net):
				errors.append({"code": "010505", "message": "cap and insp must add up to the bill without taxes", "errorType": "ERROR"})
		if header.get("ins") in (2, 3, 4) and not header.get("irtaxid"):
			errors.append({"code": "010404", "message": "irtaxid is mandatory", "errorType": "ERROR"})
		return errors

	# -- HTTP -----------------------------------------------------------------------------------
	def _handler(self):
		mock = self

		class Handler(BaseHTTPRequestHandler):
			def log_message(self, *args):
				pass

			def reply(self, status, body):
				data = json.dumps(body).encode()
				self.send_response(status)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(data)))
				self.end_headers()
				self.wfile.write(data)

			def authorized(self) -> bool:
				try:
					mock.check_token(self.headers.get("Authorization", ""))
					return True
				except Exception as error:
					self.reply(401, {"error": f"{type(error).__name__}: {error}"})
					return False

			def do_GET(self):
				url = urlparse(self.path)
				if url.path.endswith("/nonce"):
					nonce = str(uuid.uuid4())
					mock.nonces.add(nonce)
					return self.reply(200, {"nonce": nonce, "expDate": "2099-01-01T00:00:00Z"})
				if not self.authorized():
					return
				if url.path.endswith("/server-information"):
					der = mock.server_key.public_key().public_bytes(
						serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
					)
					key = {"key": base64.b64encode(der).decode(), "id": mock.key_id, "algorithm": "RSA", "purpose": 1}
					return self.reply(200, {"serverTime": 0, "publicKeys": [key]})
				if url.path.endswith("/inquiry-by-reference-id"):
					wanted = parse_qs(url.query)["referenceIds"]
					return self.reply(200, [mock.results[ref] for ref in wanted])
				self.reply(404, {})

			def do_POST(self):
				if not self.authorized():
					return
				packets = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
				result = []
				for packet in packets:
					reference = str(uuid.uuid4())
					invoice = mock.open_jws(mock.open_jwe(packet["payload"]))
					errors = mock.judge(invoice)
					mock.invoices[reference] = invoice
					mock.results[reference] = {
						"referenceNumber": reference,
						"uid": packet["header"]["requestTraceId"],
						"status": "FAILED" if errors else "SUCCESS",
						"data": {"error": errors, "warning": [], "success": not errors},
						"fiscalId": packet["header"]["fiscalId"],
					}
					result.append({"uid": packet["header"]["requestTraceId"], "referenceNumber": reference, "packetType": None, "data": None})
				self.reply(200, {"timestamp": 0, "result": result})

		return Handler
