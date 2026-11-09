"""Signing and encryption the Moadian (Iranian tax) API asks for: JWS with RS256, JWE with
RSA-OAEP-256 and A256GCM. Spec: RC_TICS.IS_v1.6, sections 5 and 7. The headers also carry typ and cty
like the official Java SDK (tax-collect-data-sdk 2.0.33) sends them."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encode_base64url(data: bytes) -> str:
	return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode_base64url(text: str) -> bytes:
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _compact_json(value: dict) -> bytes:
	return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load_private_key(pem: str):
	return serialization.load_pem_private_key(pem.encode(), password=None)


def load_certificate(pem: str) -> x509.Certificate:
	return x509.load_pem_x509_certificate(pem.encode())


def load_server_public_key(base64_der: str):
	return serialization.load_der_public_key(base64.b64decode(base64_der))


def signature_time(moment: datetime | None = None) -> str:
	moment = moment or datetime.now(timezone.utc)
	return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign_jws(payload: dict, private_key, certificate: x509.Certificate, signed_at: str | None = None) -> str:
	"""A compact JWS of the payload. Both the token and the invoice are signed this way."""
	header = {
		"alg": "RS256",
		"x5c": [base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()],
		"sigT": signed_at or signature_time(),
		"typ": "jose",
		"cty": "text/plain",
		"crit": ["sigT"],
	}
	signing_input = f"{encode_base64url(_compact_json(header))}.{encode_base64url(_compact_json(payload))}"
	signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
	return f"{signing_input}.{encode_base64url(signature)}"


def encrypt_jwe(plaintext: str, server_public_key, key_id: str) -> str:
	"""A compact JWE that only the Moadian server can open."""
	header = encode_base64url(_compact_json({"alg": "RSA-OAEP-256", "enc": "A256GCM", "kid": key_id}))
	content_key, initialization_vector = AESGCM.generate_key(bit_length=256), os.urandom(12)
	sealed = AESGCM(content_key).encrypt(initialization_vector, plaintext.encode(), header.encode("ascii"))
	ciphertext, tag = sealed[:-16], sealed[-16:]
	oaep = padding.OAEP(
		mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None
	)
	encrypted_key = server_public_key.encrypt(content_key, oaep)
	parts = (header, encrypted_key, initialization_vector, ciphertext, tag)
	return ".".join([header, *(encode_base64url(part) for part in parts[1:])])
