"""The Moadian collection API (RC_TICS.IS_v1.6): token, public key, send and inquiry.

Every call asks for a fresh one-time nonce and signs a new identity token with the company key.
A failed call raises; the caller (the Send button or the status job) is what retries.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
import requests

from erpnext_iran import moadian_crypto as crypto

LIVE_URL = "https://tp.tax.gov.ir/requestsmanager/api/v2"
TIMEOUT = 30
TEHRAN = ZoneInfo("Asia/Tehran")


def pem_from_text(text: str, label: str) -> str:
	"""A PEM rebuilt from pasted text: a Password field loses the line breaks."""
	body = re.sub(r"-----[A-Z ]+-----|\s", "", text)
	lines = [body[start : start + 64] for start in range(0, len(body), 64)]
	return "\n".join([f"-----BEGIN {label}-----", *lines, f"-----END {label}-----", ""])


def tehran_time(moment: datetime) -> str:
	"""The 2023-05-14T00:00:00.000000000+03:30 form the inquiry calls ask for."""
	text = moment.astimezone(TEHRAN).strftime("%Y-%m-%dT%H:%M:%S.000000000%z")
	return f"{text[:-2]}:{text[-2:]}"


class MoadianClient:
	def __init__(self, company: str):
		doc = frappe.get_cached_doc("Company", company)
		self.memory_id = doc.moadian_memory_id
		self.base_url = (doc.get("moadian_base_url") or LIVE_URL).rstrip("/")
		if not (self.memory_id and doc.get("moadian_certificate")):
			frappe.throw(f"Set the Moadian memory ID, private key and certificate on Company {company}.")
		self.private_key = crypto.load_private_key(
			pem_from_text(doc.get_password("moadian_private_key"), "PRIVATE KEY")
		)
		self.certificate = crypto.load_certificate(pem_from_text(doc.moadian_certificate, "CERTIFICATE"))

	def _headers(self) -> dict:
		nonce = self._get("nonce", params={"timeToLive": 20}, authorized=False)["nonce"]
		token = crypto.sign_jws({"nonce": nonce, "clientId": self.memory_id}, self.private_key, self.certificate)
		return {"Authorization": f"Bearer {token}"}

	def _get(self, path: str, params: dict | None = None, authorized: bool = True):
		headers = self._headers() if authorized else {}
		response = requests.get(f"{self.base_url}/{path}", params=params, headers=headers, timeout=TIMEOUT)
		response.raise_for_status()
		return response.json()

	def server_key(self) -> dict:
		return self._get("server-information")["publicKeys"][0]

	def send(self, invoice: dict) -> tuple[str, str]:
		"""Sign, encrypt and send one invoice. Returns (request ID, reference number)."""
		key = self.server_key()
		signed = crypto.sign_jws(invoice, self.private_key, self.certificate)
		encrypted = crypto.encrypt_jwe(signed, crypto.load_server_public_key(key["key"]), key["id"])
		request_id = str(uuid.uuid4())
		packet = {"payload": encrypted, "header": {"requestTraceId": request_id, "fiscalId": self.memory_id}}
		response = requests.post(
			f"{self.base_url}/invoice", json=[packet], headers=self._headers(), timeout=TIMEOUT
		)
		response.raise_for_status()
		return request_id, response.json()["result"][0]["referenceNumber"]

	def inquire(self, reference_number: str, sent_at: datetime) -> dict:
		"""The inquiry result of one reference number. A week back is the most the API allows."""
		params = {
			"referenceIds": reference_number,
			"start": tehran_time(sent_at),
			"end": tehran_time(datetime.now(TEHRAN)),
		}
		return self._get("inquiry-by-reference-id", params=params)[0]
