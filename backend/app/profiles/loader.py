from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MessageType, NegativeMutation
from app.domain.models import ProfileDetail, ProfileSummary, SettlementScenario


class SenderReferenceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_length: int = Field(alias="maxLength")
    uppercase: bool = True


class ProfileValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_reference: SenderReferenceRule = Field(alias="senderReference")


class FinEnvelopeProfile(BaseModel):
    """Configured FIN interface values for a client profile.

    Every value here is supplied by a human configuring the profile, which is why the
    studio classifies them as PROFILE_CONFIGURED rather than inventing them. Session and
    sequence numbers are normally allocated by the messaging interface; a profile that
    does not configure them cannot produce a complete FIN application message and the
    studio fails closed instead of fabricating a value.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sender_logical_terminal: str = Field(
        alias="senderLogicalTerminal", min_length=12, max_length=12
    )
    receiver_address: str = Field(alias="receiverAddress", min_length=12, max_length=12)
    application_id: str = Field(default="F", alias="applicationId", pattern=r"^[A-Z]$")
    service_id: str = Field(default="01", alias="serviceId", pattern=r"^\d{2}$")
    session_number: str | None = Field(default=None, alias="sessionNumber", pattern=r"^\d{4}$")
    sequence_number: str | None = Field(default=None, alias="sequenceNumber", pattern=r"^\d{6}$")
    priority: str = Field(default="N", alias="priority", pattern=r"^[NU]$")
    include_message_user_reference: bool = Field(
        default=True, alias="includeMessageUserReference"
    )
    trailer_fields: dict[str, str] = Field(default_factory=dict, alias="trailerFields")
    notes: str = Field(
        default=(
            "Session and sequence numbers are configured test-interface values, not values "
            "allocated by a live Swift interface."
        ),
        alias="notes",
    )


class MxEnvelopeProfile(BaseModel):
    """Configured ISO 20022 Business Application Header and transport values.

    The transport wrapper is profile-driven on purpose: the element that carries an AppHdr
    and a Document together is a market or client convention, not part of ISO 20022. A
    profile that configures no wrapper gets the AppHdr and the Document as separate
    outputs rather than an invented envelope.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_bic: str = Field(alias="fromBic", min_length=8, max_length=11)
    to_bic: str = Field(alias="toBic", min_length=8, max_length=11)
    business_service: str | None = Field(default=None, alias="businessService", max_length=35)
    priority: str | None = Field(default=None, alias="priority", max_length=4)
    wrapper_element: str | None = Field(default=None, alias="wrapperElement", max_length=64)


class ClientProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    profile_id: str = Field(alias="profileId")
    name: str
    version: str
    standards_release: str = Field(alias="standardsRelease")
    status: str
    supported_message_types: list[MessageType] = Field(alias="supportedMessageTypes")
    defaults: dict[str, Any]
    allowed_currencies: list[str] = Field(alias="allowedCurrencies")
    required_fields: dict[str, list[str]] = Field(alias="requiredFields")
    client_required_fields: dict[str, list[str]] = Field(alias="clientRequiredFields")
    enabled_negative_mutations: list[NegativeMutation] = Field(alias="enabledNegativeMutations")
    validation: ProfileValidation
    fin_envelope: FinEnvelopeProfile | None = Field(default=None, alias="finEnvelope")
    mx_envelope: MxEnvelopeProfile | None = Field(default=None, alias="mxEnvelope")

    def summary(self) -> ProfileSummary:
        return ProfileSummary(
            profile_id=self.profile_id,
            name=self.name,
            version=self.version,
            standards_release=self.standards_release,
            status=self.status,
            supported_message_types=self.supported_message_types,
        )

    def detail(self) -> ProfileDetail:
        return ProfileDetail(
            **self.summary().model_dump(),
            defaults=self.defaults,
            allowed_currencies=self.allowed_currencies,
            required_fields=self.required_fields,
            client_required_fields=self.client_required_fields,
            enabled_negative_mutations=self.enabled_negative_mutations,
            sender_reference_max_length=self.validation.sender_reference.max_length,
            sender_reference_uppercase=self.validation.sender_reference.uppercase,
        )

    def requirements_for(self, message_type: MessageType) -> list[str]:
        base = self.required_fields.get(message_type.value, [])
        client = self.client_required_fields.get(message_type.value, [])
        return list(dict.fromkeys([*base, *client]))

    def apply_defaults(self, scenario: SettlementScenario) -> SettlementScenario:
        payload = scenario.model_dump(mode="python", by_alias=False)
        for path, value in self.defaults.items():
            if _get_path(payload, path) in (None, ""):
                _set_path(payload, path, deepcopy(value))
        return SettlementScenario.model_validate(payload)


def _get_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = payload
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


class ProfileRepository:
    def __init__(self, config_dir: Path | None = None) -> None:
        self._config_dir = config_dir or Path(__file__).resolve().parents[2] / "config" / "profiles"
        self._profiles = self._load()

    def _load(self) -> dict[str, ClientProfile]:
        profiles: dict[str, ClientProfile] = {}
        for path in sorted(self._config_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as handle:
                profile = ClientProfile.model_validate(yaml.safe_load(handle))
            if profile.profile_id in profiles:
                raise ValueError(f"Duplicate profile ID: {profile.profile_id}")
            profiles[profile.profile_id] = profile
        if not profiles:
            raise RuntimeError("No client profiles are configured")
        return profiles

    def list(self) -> list[ClientProfile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> ClientProfile:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"Unknown profile: {profile_id}") from exc


profiles = ProfileRepository()
