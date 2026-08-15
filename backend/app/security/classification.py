from __future__ import annotations

from app.authoring.models import DataClassification
from app.specifications.models import FieldSpecification

SENSITIVE_BUSINESS_TERMS = {
    "account",
    "agent",
    "party",
    "reference",
    "security",
    "identifier",
    "amount",
    "quantity",
    "counterparty",
}


def classify_field(field: FieldSpecification) -> DataClassification:
    searchable = f"{field.business_path} {field.business_name}".lower()
    if any(term in searchable for term in SENSITIVE_BUSINESS_TERMS):
        return DataClassification.FINANCIAL_SENSITIVE
    return DataClassification.CONFIDENTIAL


def mask_value(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{'*' * min(12, len(value) - 4)}{value[-4:]}"
