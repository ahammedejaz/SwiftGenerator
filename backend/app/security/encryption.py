from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


@dataclass(frozen=True)
class EnvelopeEncryptor:
    key_id: str
    wrapping_key: bytes

    @classmethod
    def from_settings(cls, settings: Settings) -> EnvelopeEncryptor:
        if settings.data_encryption_key is None:
            raise RuntimeError("Field encryption is not configured")
        key = _decode(settings.data_encryption_key.get_secret_value())
        if len(key) != 32:
            raise RuntimeError("Field encryption key length is invalid")
        return cls(key_id=settings.data_encryption_key_id, wrapping_key=key)

    def encrypt(self, value: str, *, associated_data: str) -> str:
        data_key = AESGCM.generate_key(bit_length=256)
        data_nonce = os.urandom(12)
        wrap_nonce = os.urandom(12)
        aad = associated_data.encode("utf-8")
        ciphertext = AESGCM(data_key).encrypt(data_nonce, value.encode("utf-8"), aad)
        wrapped_key = AESGCM(self.wrapping_key).encrypt(wrap_nonce, data_key, aad)
        return json.dumps(
            {
                "v": 1,
                "kid": self.key_id,
                "dn": _encode(data_nonce),
                "wn": _encode(wrap_nonce),
                "dek": _encode(wrapped_key),
                "ct": _encode(ciphertext),
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    def decrypt(self, envelope: str, *, associated_data: str) -> str:
        payload = json.loads(envelope)
        if payload.get("v") != 1 or payload.get("kid") != self.key_id:
            raise ValueError("Unsupported encrypted value envelope")
        if set(payload) != {"v", "kid", "dn", "wn", "dek", "ct"}:
            raise ValueError("Encrypted value envelope contains unknown properties")
        aad = associated_data.encode("utf-8")
        data_key = AESGCM(self.wrapping_key).decrypt(
            _decode(payload["wn"]), _decode(payload["dek"]), aad
        )
        plaintext = AESGCM(data_key).decrypt(_decode(payload["dn"]), _decode(payload["ct"]), aad)
        return plaintext.decode("utf-8")
