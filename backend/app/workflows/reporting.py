from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from app.domain.models import ApiModel, ValidationReport
from app.knowledge.loader import TagKnowledgeRepository
from app.knowledge.models import WorkflowModuleId
from app.persistence.workflow_messages import WorkflowMessageRepository
from app.profiles.loader import ProfileRepository


class ReportedTag(ApiModel):
    knowledge_id: str
    sequence: str
    tag: str
    qualifier: str | None = None
    display_name: str
    business_meaning: str
    presence: str
    source_type: str
    source_reference: str
    review_status: str
    knowledge_version: str


class WorkflowExecutionReport(ApiModel):
    message_id: str
    workflow_id: str
    workflow_module: WorkflowModuleId
    message_type: str
    business_status: str
    related_workflow_message_id: str | None = None
    related_settlement_message_id: str | None = None
    profile_id: str
    profile_version: str
    standards_release: str
    validation: ValidationReport
    tags: list[ReportedTag]
    ai_source: str = "DETERMINISTIC"
    cache_hit: bool = False
    api_calls_used: int = 0
    api_calls_avoided: int = 0
    tokens_used: int = 0
    tokens_avoided: int = 0
    provider_reported_cost: str | None = None
    estimated_cost_avoided: str | None = None
    latency_ms: int = 0
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclaimer: str


class WorkflowReportingService:
    def __init__(
        self,
        messages: WorkflowMessageRepository,
        profiles: ProfileRepository,
        knowledge: TagKnowledgeRepository,
    ) -> None:
        self._messages = messages
        self._profiles = profiles
        self._knowledge = knowledge

    def report(self, message_id: str) -> WorkflowExecutionReport:
        message = self._messages.get(message_id)
        profile = self._profiles.get(message.profile_id)
        available = {
            (
                item.record.sequence_path,
                item.record.field_tag,
                item.record.qualifier,
            ): item
            for item in self._knowledge.list_records(
                message_type=message.resolved_message_type,
                profile_id=message.profile_id,
            )
        }
        tags: list[ReportedTag] = []
        for field in message.field_map:
            effective = available.get((field.sequence, field.tag, field.qualifier))
            if effective is None:
                raise ValueError(
                    "Generated workflow field has no verified knowledge record: "
                    f"{field.sequence}/{field.tag}/{field.qualifier or 'NONE'}"
                )
            record = effective.record
            tags.append(
                ReportedTag(
                    knowledge_id=record.knowledge_id,
                    sequence=field.sequence,
                    tag=field.tag,
                    qualifier=field.qualifier,
                    display_name=record.display_name,
                    business_meaning=record.business_meaning,
                    presence=effective.effective_presence.value,
                    source_type=record.source.source_type.value,
                    source_reference=record.source.source_reference,
                    review_status=record.source.review_status.value,
                    knowledge_version=record.knowledge_version,
                )
            )
        status = str(message.canonical_data.get("businessStatus", message.resolved_message_type))
        return WorkflowExecutionReport(
            message_id=message.message_id,
            workflow_id=message.workflow_id,
            workflow_module=message.workflow_module,
            message_type=message.resolved_message_type.value,
            business_status=status,
            related_workflow_message_id=message.related_workflow_message_id,
            related_settlement_message_id=message.related_settlement_message_id,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            standards_release=profile.standards_release,
            validation=message.validation,
            tags=tags,
            disclaimer=message.disclaimer,
        )
