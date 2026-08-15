from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from app.domain.enums import MessageType
from app.domain.models import ApiModel, RenderedField, ValidationReport
from app.knowledge.models import WorkflowModuleId
from app.services.generation import DISCLAIMER


class WorkflowGeneratedMessage(ApiModel):
    message_id: str
    workflow_id: str
    workflow_module: WorkflowModuleId
    resolved_message_type: MessageType
    canonical_data: dict[str, Any]
    raw_message: str
    field_map: list[RenderedField]
    profile_id: str
    profile_version: str
    validation: ValidationReport
    disclaimer: str = DISCLAIMER
    related_workflow_message_id: str | None = None
    related_settlement_message_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowLifecycleEntry(ApiModel):
    message_id: str
    message_type: MessageType
    workflow_module: WorkflowModuleId
    business_status: str
    related_workflow_message_id: str | None = None
    related_settlement_message_id: str | None = None
    validation_status: str
    created_at: datetime


class WorkflowLifecycle(ApiModel):
    workflow_id: str
    entries: list[WorkflowLifecycleEntry]
    correlation_valid: bool
    correlation_findings: list[str] = Field(default_factory=list)
