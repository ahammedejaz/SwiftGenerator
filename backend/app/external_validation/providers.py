from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ValidationEvidence:
    message_checksum: str
    provider_type: str
    profile_id: str
    standards_release: str
    passed: bool
    validated_at: datetime
    safe_findings: list[dict[str, str]]


class ExternalValidationAdapter(Protocol):
    async def validate(self, message: bytes, checksum: str) -> ValidationEvidence: ...


class UploadedEvidenceAdapter:
    """Correlates authorised evidence; it does not call MyStandards or a network."""

    def verify_correlation(self, evidence: ValidationEvidence, expected_checksum: str) -> None:
        if evidence.message_checksum != expected_checksum:
            raise ValueError("External validation evidence checksum mismatch")
