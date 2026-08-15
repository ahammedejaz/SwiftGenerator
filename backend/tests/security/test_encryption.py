import json

import pytest
from cryptography.exceptions import InvalidTag

from app.config import get_settings
from app.security.encryption import EnvelopeEncryptor


def test_envelope_encryption_uses_random_data_keys_and_authenticated_context() -> None:
    encryptor = EnvelopeEncryptor.from_settings(get_settings())
    first = encryptor.encrypt("REAL-ACCOUNT-1234", associated_data="tenant:draft:field")
    second = encryptor.encrypt("REAL-ACCOUNT-1234", associated_data="tenant:draft:field")
    assert first != second
    assert "REAL-ACCOUNT-1234" not in first
    payload = json.loads(first)
    assert set(payload) == {"v", "kid", "dn", "wn", "dek", "ct"}
    assert encryptor.decrypt(first, associated_data="tenant:draft:field") == "REAL-ACCOUNT-1234"
    with pytest.raises(InvalidTag):
        encryptor.decrypt(first, associated_data="another-tenant:draft:field")


def test_encrypted_value_rejects_unknown_envelope_properties() -> None:
    encryptor = EnvelopeEncryptor.from_settings(get_settings())
    envelope = json.loads(encryptor.encrypt("VALUE", associated_data="aad"))
    envelope["unexpected"] = "value"
    with pytest.raises(ValueError, match="unknown properties"):
        encryptor.decrypt(json.dumps(envelope), associated_data="aad")
