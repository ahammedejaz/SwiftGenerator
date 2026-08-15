from __future__ import annotations

import html
import io
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass

from app.authoring.composer import ComposeField, GenericComposition, specification_composer
from app.authoring.models import (
    ComposeResponse,
    DownloadFormat,
    DraftResponse,
    FinEnvelopeRequest,
    OutputMode,
    PlatformRole,
    SessionUser,
    ValidationLevel,
    ValidationLevelState,
)
from app.authoring.repository import AuthoringRepository
from app.config import Settings
from app.domain.enums import MessageType
from app.knowledge.loader import knowledge_repository
from app.knowledge.models import PresenceRule
from app.persistence.models import MessageDraftRecord
from app.profiles.loader import ClientProfile, profiles
from app.specifications.models import CapabilityState, MessageSpecification
from app.specifications.registry import specification_registry

AUTHORING_DISCLAIMER = (
    "Generated against a configured source-bounded ISO 15022 subset. No SWIFT certification "
    "or universal market acceptance is claimed. External and institution-specific validation "
    "may be required before authorised submission."
)

ADDRESS_PATTERN = re.compile(r"^[A-Z0-9]{12}$")


@dataclass(frozen=True)
class DownloadArtifact:
    content: bytes
    media_type: str
    filename: str


class AuthoringService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = AuthoringRepository(settings, specification_registry, profiles)

    def compose(self, user: SessionUser, draft_id: str) -> ComposeResponse:
        draft, specification, sequences, fields = self.repository.load_for_composition(
            user, draft_id
        )
        profile = profiles.get(draft.profile_id)
        specification = self._effective_specification(specification, profile)
        composition = specification_composer.compose(
            specification,
            sequences,
            fields,
            client_profile_enabled=MessageType(draft.message_type)
            in profile.supported_message_types,
        )
        profile_findings = self._profile_findings(fields, profile)
        if profile_findings:
            levels = dict(composition.validation_levels)
            levels[ValidationLevel.CLIENT_PROFILE_VALID] = ValidationLevelState.FAILED
            composition = GenericComposition(
                block_4=composition.block_4,
                checksum=composition.checksum,
                line_mappings=composition.line_mappings,
                validation_levels=levels,
                findings=[*composition.findings, *profile_findings],
            )
        snapshot: dict[str, object] = {
            "messageType": draft.message_type,
            "profileId": draft.profile_id,
            "profileVersion": draft.profile_version,
            "standardsRelease": draft.standards_release,
            "block4": composition.block_4,
            "checksum": composition.checksum,
            "fieldSources": [
                {"rowId": item.row.row_id, "source": item.source.value} for item in fields
            ],
        }
        self.repository.save_composition(
            user,
            draft_id,
            composition.checksum,
            composition.validation_levels,
            composition.findings,
            snapshot,
        )
        return self._response(draft, specification.capability, composition)

    @staticmethod
    def _effective_specification(
        specification: MessageSpecification, profile: ClientProfile
    ) -> MessageSpecification:
        required = {
            path.replace("_", "").lower()
            for path in profile.requirements_for(specification.message_type)
        }
        effective_fields = []
        for row in specification.fields:
            effective = knowledge_repository.effective(row.knowledge_id, profile.profile_id)
            is_required = (
                row.business_path.replace("_", "").lower() in required
                or effective.effective_presence is PresenceRule.MANDATORY
            )
            effective_fields.append(
                row.model_copy(
                    update={
                        "presence": effective.effective_presence,
                        "min_occurs": 1 if is_required else 0,
                        "allowed_options": effective.effective_options,
                        "allowed_codes": effective.effective_codes,
                    }
                )
            )
        return specification.model_copy(update={"fields": effective_fields})

    @staticmethod
    def _profile_findings(fields: list[ComposeField], profile: ClientProfile) -> list[str]:
        findings: list[str] = []
        for field in fields:
            if field.row.business_path == "senderReference":
                if len(field.value) > profile.validation.sender_reference.max_length:
                    findings.append("Sender reference exceeds the effective client-profile length.")
                if (
                    profile.validation.sender_reference.uppercase
                    and field.value != field.value.upper()
                ):
                    findings.append("Sender reference must be uppercase for this profile.")
            if field.row.tag in {"11A", "19A", "19B"}:
                value = field.value.removeprefix("N")
                currency = value[:3]
                if currency.isalpha() and currency not in profile.allowed_currencies:
                    findings.append(
                        f"Currency {currency} is not enabled by the selected client profile."
                    )
        return findings

    @staticmethod
    def _response(
        draft: MessageDraftRecord,
        capability: CapabilityState,
        composition: GenericComposition,
    ) -> ComposeResponse:
        return ComposeResponse(
            draft_id=draft.id,
            revision=draft.revision,
            message_type=MessageType(draft.message_type),
            block_4=composition.block_4,
            checksum=composition.checksum,
            line_mappings=composition.line_mappings,
            validation_levels=composition.validation_levels,
            findings=composition.findings,
            capability=capability,
            disclaimer=AUTHORING_DISCLAIMER,
        )

    def get_draft(self, user: SessionUser, draft_id: str) -> DraftResponse:
        return self.repository.get_draft(user, draft_id)

    def download(
        self,
        user: SessionUser,
        draft_id: str,
        download_format: DownloadFormat,
        envelope: FinEnvelopeRequest | None = None,
    ) -> DownloadArtifact:
        composed = self.compose(user, draft_id)
        safe_stem = f"{composed.message_type.value}_{draft_id}_{composed.revision}"
        metadata: dict[str, object] = {
            "draftId": draft_id,
            "messageType": composed.message_type.value,
            "revision": composed.revision,
            "checksum": composed.checksum,
            "validationLevels": {
                key.value: value.value for key, value in composed.validation_levels.items()
            },
            "disclaimer": AUTHORING_DISCLAIMER,
        }
        if download_format in {DownloadFormat.BLOCK4, DownloadFormat.TXT}:
            suffix = "fin" if download_format is DownloadFormat.BLOCK4 else "txt"
            return DownloadArtifact(
                content=composed.block_4.encode(),
                media_type="text/plain; charset=utf-8",
                filename=f"{safe_stem}.{suffix}",
            )
        if download_format is DownloadFormat.FIN:
            if envelope is None or envelope.output_mode is not OutputMode.FIN_APPLICATION_MESSAGE:
                raise ValueError("A complete FIN envelope request is required")
            full_fin = self._fin_message(composed, envelope)
            return DownloadArtifact(
                content=full_fin.encode(),
                media_type="text/plain; charset=utf-8",
                filename=f"{safe_stem}.fin",
            )
        if download_format is DownloadFormat.RJE:
            if not self.settings.rje_export_enabled:
                raise ValueError(
                    "RJE export is disabled until an authorised client interchange "
                    "contract is configured"
                )
            if envelope is None or envelope.output_mode is not OutputMode.RJE_SINGLE:
                raise ValueError("An RJE envelope request is required")
            full_fin = self._fin_message(composed, envelope)
            return DownloadArtifact(
                content=(full_fin + "\r\n").encode(),
                media_type="application/octet-stream",
                filename=f"{safe_stem}.rje",
            )
        draft = self.repository.get_draft(user, draft_id)
        if download_format is DownloadFormat.CANONICAL_JSON:
            payload = {
                **metadata,
                "profileId": draft.profile_id,
                "profileVersion": draft.profile_version,
                "standardsRelease": draft.standards_release,
                "sequences": [
                    item.model_dump(mode="json", by_alias=True) for item in draft.sequences
                ],
                "fields": [item.model_dump(mode="json", by_alias=True) for item in draft.fields],
            }
            return DownloadArtifact(
                content=json.dumps(payload, indent=2).encode(),
                media_type="application/json",
                filename=f"{safe_stem}.canonical.json",
            )
        if download_format is DownloadFormat.VALIDATION_JSON:
            return DownloadArtifact(
                content=json.dumps(metadata, indent=2).encode(),
                media_type="application/json",
                filename=f"{safe_stem}.validation.json",
            )
        if download_format is DownloadFormat.VALIDATION_HTML:
            body = self._validation_html(metadata)
            return DownloadArtifact(
                content=body.encode(),
                media_type="text/html; charset=utf-8",
                filename=f"{safe_stem}.validation.html",
            )
        if download_format is DownloadFormat.EVIDENCE_ZIP:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f"{safe_stem}.fin", composed.block_4)
                archive.writestr(f"{safe_stem}.validation.json", json.dumps(metadata, indent=2))
                archive.writestr(f"{safe_stem}.validation.html", self._validation_html(metadata))
            return DownloadArtifact(
                content=buffer.getvalue(),
                media_type="application/zip",
                filename=f"{safe_stem}.evidence.zip",
            )
        raise ValueError("The requested download format is unsupported")

    def _fin_message(self, composed: ComposeResponse, envelope: FinEnvelopeRequest) -> str:
        if not self.settings.fin_export_enabled:
            raise ValueError("FIN envelope export is disabled")
        if not envelope.sender_logical_terminal or not ADDRESS_PATTERN.fullmatch(
            envelope.sender_logical_terminal
        ):
            raise ValueError("A 12-character configured sender logical terminal is required")
        if not envelope.receiver_address or not ADDRESS_PATTERN.fullmatch(
            envelope.receiver_address
        ):
            raise ValueError("A 12-character configured receiver address is required")
        if not envelope.session_number or not envelope.sequence_number:
            raise ValueError(
                "Session and sequence values must be supplied by the authorised interface"
            )
        block_1 = (
            f"{{1:F01{envelope.sender_logical_terminal}"
            f"{envelope.session_number}{envelope.sequence_number}}}"
        )
        block_2 = (
            f"{{2:I{composed.message_type.value[2:]}"
            f"{envelope.receiver_address}{envelope.priority}}}"
        )
        block_3 = (
            f"{{3:{{108:{envelope.message_user_reference}}}}}"
            if envelope.message_user_reference
            else ""
        )
        return f"{block_1}{block_2}{block_3}{composed.block_4}"

    @staticmethod
    def _validation_html(metadata: Mapping[str, object]) -> str:
        rows = "".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            for key, value in metadata.items()
        )
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Validation evidence</title></head><body>"
            f"<h1>Validation evidence</h1><table>{rows}</table></body></html>"
        )

    @staticmethod
    def ensure_submission_eligible(composed: ComposeResponse) -> None:
        for level in (
            ValidationLevel.CANONICAL_VALID,
            ValidationLevel.STRUCTURE_VALID,
            ValidationLevel.FORMAT_VALID,
            ValidationLevel.CLIENT_PROFILE_VALID,
        ):
            if composed.validation_levels[level] is not ValidationLevelState.PASSED:
                raise ValueError(f"Submission requires {level.value}")


def can_view_unmasked(user: SessionUser) -> bool:
    return bool(
        user.roles
        & {
            PlatformRole.AUTHOR,
            PlatformRole.REVIEWER,
            PlatformRole.APPROVER,
            PlatformRole.SUBMITTER,
            PlatformRole.SECURITY_ADMIN,
        }
    )
