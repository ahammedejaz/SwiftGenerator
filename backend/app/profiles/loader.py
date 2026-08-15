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
