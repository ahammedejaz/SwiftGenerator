from pathlib import Path

import yaml
from pydantic import Field

from app.domain.enums import MessageType
from app.domain.models import ApiModel
from app.specifications.models import CapabilityState, SpecificationSource


class CatalogueEvent(ApiModel):
    event_code: str
    name: str
    capability: CapabilityState = CapabilityState.CATALOGUE_ONLY
    message: str = "Event visible; validated generation profile not imported."


class CorporateActionEventProfile(ApiModel):
    profile_id: str
    version: str
    event_code: str
    name: str
    capability: CapabilityState
    standards_release: str
    allowed_message_types: list[MessageType]
    allowed_classifications: list[str]
    allowed_option_codes: list[str]
    required_rows: dict[MessageType, list[str]]
    source: SpecificationSource
    catalogue_only_events: list[CatalogueEvent] = Field(default_factory=list)


class EventProfileRegistry:
    def __init__(self, path: Path | None = None) -> None:
        path = path or (
            Path(__file__).resolve().parents[2] / "config" / "event_profiles" / "dvop_v1.yaml"
        )
        with path.open(encoding="utf-8") as source:
            self.profile = CorporateActionEventProfile.model_validate(yaml.safe_load(source))
        if self.profile.capability is CapabilityState.PRODUCTION_CAPABLE:
            raise ValueError("A source-bounded profile cannot self-assert production capability")

    def list(self) -> list[CorporateActionEventProfile]:
        return [self.profile]


event_profile_registry = EventProfileRegistry()
