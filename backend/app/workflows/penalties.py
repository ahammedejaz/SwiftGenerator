from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from app.domain.enums import (
    AmountDirection,
    MessageType,
    PenaltyAction,
    PenaltyListType,
    PenaltyStatus,
    PenaltyType,
    Severity,
    ValidationStatus,
)
from app.domain.models import ApiModel, ValidationFinding, ValidationReport
from app.knowledge.models import WorkflowModuleId
from app.persistence.repository import MessageRepository
from app.persistence.workflow_messages import WorkflowMessageRepository
from app.profiles.loader import ProfileRepository
from app.workflows.models import WorkflowGeneratedMessage

REFERENCE_PATTERN = re.compile(r"^(?!/)(?!.*//)[A-Z0-9._-]{1,16}(?<!/)$")
IDENTIFIER_PATTERN = re.compile(r"^[A-Z0-9._-]{3,34}$")


class PenaltyEntry(ApiModel):
    penalty_reference: str
    common_reference: str | None = None
    previous_penalty_reference: str | None = None
    related_instruction_reference: str | None = None
    penalty_type: PenaltyType
    action: PenaltyAction
    status: PenaltyStatus
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount: Decimal = Field(ge=0)
    amount_direction: AmountDirection
    detection_date: date
    number_of_days: int = Field(ge=0, le=999)

    @field_validator(
        "penalty_reference",
        "common_reference",
        "previous_penalty_reference",
        "related_instruction_reference",
    )
    @classmethod
    def validate_reference(cls, value: str | None) -> str | None:
        if value is not None and not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value

    @model_validator(mode="after")
    def validate_action_status(self) -> PenaltyEntry:
        if self.action == PenaltyAction.REMOVED and self.status != PenaltyStatus.REMOVED:
            raise ValueError("A removed penalty must use REMOVED status")
        if self.status == PenaltyStatus.REMOVED and self.action != PenaltyAction.REMOVED:
            raise ValueError("REMOVED status is reserved for a removed penalty")
        return self


class PenaltyStatement(ApiModel):
    workflow_id: str
    profile_id: str = "BASE_DEMO_V1"
    statement_reference: str
    statement_date: date
    safekeeping_account: str = Field(min_length=3, max_length=35)
    account_servicer: str
    related_party: str
    list_type: PenaltyListType
    penalties: list[PenaltyEntry] = Field(min_length=1, max_length=100)
    synthetic_data: bool = True

    @field_validator("statement_reference")
    @classmethod
    def validate_statement_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("Statement reference uses the supported 1–16 character subset")
        return value

    @field_validator("account_servicer", "related_party")
    @classmethod
    def validate_party(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("Party identifiers use the synthetic proprietary subset")
        return value

    @model_validator(mode="after")
    def require_synthetic_and_consistent_group(self) -> PenaltyStatement:
        if not self.synthetic_data:
            raise ValueError("Only synthetic penalty statements are supported")
        if len({(item.currency, item.detection_date) for item in self.penalties}) != 1:
            raise ValueError("The supported MT537 subset groups one currency and detection date")
        expected_actions = {
            PenaltyListType.NEW_ONLY: {PenaltyAction.NEW},
            PenaltyListType.UPDATED_OR_REMOVED: {
                PenaltyAction.UPDATED,
                PenaltyAction.REMOVED,
            },
        }.get(self.list_type)
        if expected_actions and any(item.action not in expected_actions for item in self.penalties):
            raise ValueError("Penalty actions do not match the selected list type")
        references = [item.penalty_reference for item in self.penalties]
        if len(references) != len(set(references)):
            raise ValueError("Penalty references must be unique within a statement")
        return self


class PenaltyGenerateRequest(ApiModel):
    statement: PenaltyStatement
    related_settlement_message_id: str | None = None


class PenaltyValidateRequest(ApiModel):
    statement: PenaltyStatement
    related_settlement_message_id: str | None = None


class PenaltyWorkflowService:
    def __init__(
        self,
        profiles: ProfileRepository,
        workflows: WorkflowMessageRepository,
        settlements: MessageRepository,
    ) -> None:
        self._profiles = profiles
        self._workflows = workflows
        self._settlements = settlements

    def validate(
        self,
        statement: PenaltyStatement,
        related_settlement_message_id: str | None = None,
    ) -> ValidationReport:
        profile = self._profiles.get(statement.profile_id)
        findings: list[ValidationFinding] = []

        def error(rule_id: str, path: str, message: str, suggestion: str) -> None:
            findings.append(
                ValidationFinding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    field_path=path,
                    message=message,
                    technical_explanation=(
                        "The verified MT537 demonstration rule rejected this value."
                    ),
                    expected_condition=suggestion,
                    suggestion=suggestion,
                )
            )

        if MessageType.MT537 not in profile.supported_message_types:
            error(
                "MT537-PROFILE",
                "profileId",
                "MT537 is disabled by this profile.",
                "Select an enabled profile.",
            )
        currencies = {item.currency for item in statement.penalties}
        if not currencies.issubset(profile.allowed_currencies):
            error(
                "MT537-CURRENCY",
                "penalties.currency",
                "A currency is not allowed by this profile.",
                "Use a profile-allowed ISO currency.",
            )
        if self._workflows.reference_exists(statement.statement_reference):
            error(
                "MT537-STATEMENT-REFERENCE",
                "statementReference",
                "Statement reference already exists.",
                "Provide a new synthetic reference.",
            )
        if related_settlement_message_id:
            try:
                settlement = self._settlements.get(related_settlement_message_id)
            except KeyError:
                error(
                    "MT537-RELATED-SETTLEMENT",
                    "relatedSettlementMessageId",
                    "Related settlement instruction was not found.",
                    "Use a persisted settlement message ID.",
                )
            else:
                related_references = {
                    item.related_instruction_reference
                    for item in statement.penalties
                    if item.related_instruction_reference
                }
                if settlement.scenario.sender_reference not in related_references:
                    error(
                        "MT537-REFERENCE-CORRELATION",
                        "penalties.relatedInstructionReference",
                        "Penalty reference does not match the selected settlement.",
                        "Use the selected instruction sender reference.",
                    )
        return ValidationReport(
            status=ValidationStatus.INVALID if findings else ValidationStatus.VALID,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            findings=findings,
            error_count=len(findings),
            warning_count=0,
        )

    def generate(self, request: PenaltyGenerateRequest) -> WorkflowGeneratedMessage:
        from app.composers.penalty_statement import PenaltyStatementComposer

        report = self.validate(request.statement, request.related_settlement_message_id)
        if report.status != ValidationStatus.VALID:
            raise ValueError(report.findings[0].message)
        composed = PenaltyStatementComposer().compose(request.statement)
        profile = self._profiles.get(request.statement.profile_id)
        generated = WorkflowGeneratedMessage(
            message_id=str(uuid4()),
            workflow_id=request.statement.workflow_id,
            workflow_module=WorkflowModuleId.PENALTIES,
            resolved_message_type=MessageType.MT537,
            canonical_data=request.statement.model_dump(mode="json", by_alias=True),
            raw_message=composed.raw_message,
            field_map=composed.field_map,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            validation=report,
            related_settlement_message_id=request.related_settlement_message_id,
        )
        self._workflows.save(generated)
        return generated
