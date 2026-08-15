from pydantic import Field

from app.authoring.models import FieldValueSource
from app.domain.enums import MessageType
from app.domain.models import ApiModel
from app.knowledge.models import PresenceRule
from app.specifications.models import CapabilityState


class SampleSummary(ApiModel):
    sample_id: str
    message_type: MessageType
    scenario: str
    profile_id: str
    profile_version: str
    standards_release: str
    capability: CapabilityState
    generated_by_production_composer: bool = True
    synthetic: bool = True


class AnnotatedSampleLine(ApiModel):
    line_number: int
    raw_line: str
    sequence_path: str
    sequence_occurrence: int
    row_id: str
    knowledge_id: str
    tag: str
    qualifier: str | None = None
    entered_value: str
    business_meaning: str
    why_used: str
    presence: PresenceRule
    source: FieldValueSource = FieldValueSource.SAMPLE_DATA


class SampleDetail(SampleSummary):
    raw_message: str
    annotations: list[AnnotatedSampleLine]
    covered_row_ids: list[str]
    known_limitations: list[str] = Field(default_factory=list)
