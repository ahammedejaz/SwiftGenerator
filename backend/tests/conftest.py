import base64
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("REPORT_DIRECTORY", "/tmp/securities-studio-test-reports")
os.environ["APP_ENV"] = "development"
os.environ["AI_PROVIDER"] = "disabled"
os.environ["REAL_DATA_MODE_ENABLED"] = "true"
os.environ["AUTH_MODE"] = "development"
os.environ["SESSION_HMAC_SECRET"] = "test-session-secret-that-is-longer-than-thirty-two"
os.environ["DATA_ENCRYPTION_KEY"] = base64.b64encode(b"T" * 32).decode()
os.environ["MOCK_UAT_CONNECTOR_ENABLED"] = "true"
os.environ["SUBMISSION_MODE"] = "uat"

from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_mt541_payload() -> dict[str, object]:
    return {
        "scenarioId": "TC-MT541-GOLDEN",
        "profileId": "BASE_DEMO_V1",
        "lifecycle": "INSTRUCTION",
        "direction": "RECEIVE",
        "paymentType": "AGAINST_PAYMENT",
        "function": "NEWM",
        "senderReference": "TEST000000001",
        "trade": {
            "transactionType": "BUY",
            "tradeDate": "2026-08-03",
            "settlementDate": "2026-08-06",
        },
        "security": {
            "identifierType": "ISIN",
            "identifier": "XS0000000001",
            "quantityType": "UNIT",
            "quantity": "1000",
        },
        "account": {"safekeepingAccount": "SYNTHSAFE01"},
        "settlement": {
            "currency": "USD",
            "amount": "25000.00",
            "placeOfSettlement": "SYNTHPSET01",
            "deliveringAgent": "SYNTHDEAG01",
            "receivingAgent": "SYNTHREAG01",
        },
        "testConfiguration": {"mode": "VALID"},
        "syntheticData": True,
    }
