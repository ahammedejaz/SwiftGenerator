from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.composers.settlement_command import SettlementCommandComposer
from app.domain.enums import (
    AmendmentClassification,
    AmendmentField,
    Lifecycle,
    MessageFunction,
    MessageType,
    ResponseAction,
    SettlementCommandType,
    SettlementResult,
    Severity,
    ValidationStatus,
)
from app.domain.models import (
    AmendmentChange,
    AmendmentDecisionRequest,
    AmendmentDecisionResponse,
    CancelRebookRequest,
    CancelRebookResponse,
    GeneratedMessage,
    LifecycleResponseRequest,
    SettlementCancellationRequest,
    SettlementCommandDetails,
    SettlementCommandRequest,
    SettlementScenario,
    TestConfiguration,
    ValidationFinding,
    ValidationReport,
)
from app.knowledge.models import KnowledgeSource, ReviewStatus
from app.persistence.repository import MessageRepository
from app.profiles.loader import ProfileRepository
from app.services.generation import DISCLAIMER, GenerationService
from app.services.lifecycle import LifecycleService

SUPPORTED_INSTRUCTIONS = {
    MessageType.MT540,
    MessageType.MT541,
    MessageType.MT542,
    MessageType.MT543,
}


class AmendmentFieldPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: AmendmentClassification
    method: str
    enabled: bool
    explanation: str = Field(min_length=10, max_length=500)


class AmendmentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    policy_id: str = Field(alias="policyId")
    version: str
    standards_release: str = Field(alias="standardsRelease")
    source: KnowledgeSource
    field_policies: dict[AmendmentField, AmendmentFieldPolicy] = Field(alias="fieldPolicies")


def load_amendment_policy(path: Path | None = None) -> AmendmentPolicy:
    configured = path or (
        Path(__file__).resolve().parents[2]
        / "config"
        / "workflows"
        / "settlement_amendment_v1.yaml"
    )
    with configured.open(encoding="utf-8") as source:
        policy = AmendmentPolicy.model_validate(yaml.safe_load(source))
    if policy.source.review_status != ReviewStatus.VERIFIED:
        raise ValueError("Enabled amendment policy must have verified provenance")
    if set(policy.field_policies) != set(AmendmentField):
        raise ValueError("Amendment policy must explicitly classify every supported field")
    return policy


class SettlementProcessingService:
    def __init__(
        self,
        profile_repository: ProfileRepository,
        message_repository: MessageRepository,
        generation_service: GenerationService,
        lifecycle_service: LifecycleService,
        policy: AmendmentPolicy | None = None,
    ) -> None:
        self._profiles = profile_repository
        self._messages = message_repository
        self._generation = generation_service
        self._lifecycle = lifecycle_service
        self._policy = policy or load_amendment_policy()
        self._command_composer = SettlementCommandComposer()

    def cancellation(self, request: SettlementCancellationRequest) -> GeneratedMessage:
        original_message = self._original_instruction(request.original_instruction_id)
        original = original_message.scenario
        if self._messages.has_active_cancellation(request.original_instruction_id):
            raise ValueError("An active cancellation request already exists")
        reference = request.cancellation_reference or self._reference("CX")
        self._require_unique_reference(reference)
        cancellation = original.model_copy(
            deep=True,
            update={
                "scenario_id": f"{original.scenario_id}-CANC",
                "function": MessageFunction.CANC,
                "sender_reference": reference,
                "related_reference": original.sender_reference,
                "confirmation": original.confirmation.model_copy(
                    update={
                        "confirmation_reference": None,
                        "actual_settlement_date": None,
                        "settled_quantity": None,
                        "settled_amount": None,
                        "settlement_result": None,
                    }
                ),
                "status": original.status.model_copy(
                    update={
                        "category": None,
                        "code": None,
                        "reason_code": None,
                        "narrative": None,
                        "related_instruction_message_type": None,
                    }
                ),
                "test_configuration": TestConfiguration(),
            },
        )
        return self._generation.generate(
            cancellation,
            related_message_id=request.original_instruction_id,
        )

    def amendment_decision(self, request: AmendmentDecisionRequest) -> AmendmentDecisionResponse:
        original = self._original_instruction(request.original_instruction_id)
        timeline = self._messages.lifecycle(original.message_id)
        if any(
            entry.lifecycle == Lifecycle.CONFIRMATION
            and entry.business_status == SettlementResult.FULL.value
            for entry in timeline.entries
        ):
            return self._decision(
                original.scenario,
                request.changes,
                AmendmentClassification.UNSUPPORTED_MODIFICATION,
                "UNSUPPORTED_AFTER_FULL_SETTLEMENT",
                "A fully settled instruction cannot be modified in this configured lifecycle.",
            )

        policies = [self._policy.field_policies[item.field_path] for item in request.changes]
        fields = {item.field_path for item in request.changes}
        if AmendmentField.CANCEL_TRANSACTION in fields and len(fields) > 1:
            return self._decision(
                original.scenario,
                request.changes,
                AmendmentClassification.CLARIFICATION_REQUIRED,
                "CLARIFICATION",
                "Cancellation cannot be combined with processing or replacement changes.",
            )
        disabled = [policy for policy in policies if not policy.enabled]
        if disabled:
            return self._decision(
                original.scenario,
                request.changes,
                AmendmentClassification.UNSUPPORTED_MODIFICATION,
                "UNSUPPORTED",
                " ".join(dict.fromkeys(item.explanation for item in disabled)),
            )
        classifications = {item.classification for item in policies}
        if len(classifications) > 1:
            return self._decision(
                original.scenario,
                request.changes,
                AmendmentClassification.CLARIFICATION_REQUIRED,
                "CLARIFICATION",
                "Submit processing changes separately from cancellation or core-data changes.",
            )
        classification = next(iter(classifications))
        method = policies[0].method
        return self._decision(
            original.scenario,
            request.changes,
            classification,
            method,
            " ".join(dict.fromkeys(item.explanation for item in policies)),
        )

    def command(self, request: SettlementCommandRequest) -> GeneratedMessage:
        original_message = self._original_instruction(request.original_instruction_id)
        original = original_message.scenario
        if request.command_type != SettlementCommandType.MODIFY_PRIORITY:
            raise ValueError("Only the source-backed MT530 priority subset is enabled")
        self._require_unique_reference(request.command_reference)
        profile = self._profiles.get(original.profile_id)
        if MessageType.MT530 not in profile.supported_message_types:
            raise ValueError("MT530 is not enabled by the selected profile")
        scenario = original.model_copy(
            deep=True,
            update={
                "scenario_id": f"{original.scenario_id}-PRIORITY",
                "lifecycle": Lifecycle.INSTRUCTION,
                "message_type": MessageType.MT530,
                "function": MessageFunction.NEWM,
                "sender_reference": request.command_reference,
                "related_reference": original.sender_reference,
                "command": SettlementCommandDetails(
                    command_type=request.command_type,
                    original_instruction_reference=original.sender_reference,
                    priority=request.priority,
                ),
                "test_configuration": TestConfiguration(),
            },
        )
        report = self.validate_command(scenario, original)
        if report.status != ValidationStatus.VALID:
            from app.services.generation import DomainValidationError

            raise DomainValidationError(report)
        composed = self._command_composer.compose(scenario, profile)
        generated = GeneratedMessage(
            message_id=str(uuid4()),
            scenario=scenario,
            resolved_message_type=MessageType.MT530,
            raw_message=composed.raw_message,
            field_map=composed.field_map,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            validation=report,
            disclaimer=DISCLAIMER,
        )
        self._messages.save(generated, related_message_id=original_message.message_id)
        return generated

    def validate_command(
        self,
        command: SettlementScenario,
        original: SettlementScenario,
    ) -> ValidationReport:
        findings: list[ValidationFinding] = []

        def require(condition: bool, rule_id: str, path: str, message: str) -> None:
            if not condition:
                findings.append(
                    ValidationFinding(
                        rule_id=rule_id,
                        severity=Severity.ERROR,
                        field_path=path,
                        message=message,
                        technical_explanation=(
                            "The source-bounded MT530 PRIR subset enforces this condition."
                        ),
                        expected_condition="A value correlated to the original instruction",
                        suggestion="Generate the command from the persisted instruction.",
                    )
                )

        require(
            command.message_type == MessageType.MT530,
            "MT530-TYPE",
            "messageType",
            "MT530 is required.",
        )
        require(
            command.function == MessageFunction.NEWM,
            "MT530-FUNCTION",
            "function",
            "The supported command uses NEWM.",
        )
        require(
            command.command.command_type == SettlementCommandType.MODIFY_PRIORITY,
            "MT530-COMMAND-TYPE",
            "command.commandType",
            "Only priority modification is supported.",
        )
        require(
            command.command.original_instruction_reference == original.sender_reference,
            "MT530-ORIGINAL-REFERENCE",
            "command.originalInstructionReference",
            "The command must reference the original instruction.",
        )
        require(
            command.account.safekeeping_account == original.account.safekeeping_account,
            "MT530-ACCOUNT-CORRELATION",
            "account.safekeepingAccount",
            "The command account must match the original instruction.",
        )
        require(
            command.command.priority is not None and 1 <= command.command.priority <= 9999,
            "MT530-PRIORITY-RANGE",
            "command.priority",
            "Priority must be from 0001 through 9999.",
        )
        profile = self._profiles.get(command.profile_id)
        return ValidationReport(
            status=ValidationStatus.INVALID if findings else ValidationStatus.VALID,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            findings=findings,
            error_count=len(findings),
            warning_count=0,
        )

    def cancel_and_rebook(self, request: CancelRebookRequest) -> CancelRebookResponse:
        decision_request = AmendmentDecisionRequest(
            original_instruction_id=request.original_instruction_id,
            changes=request.changes,
        )
        decision = self.amendment_decision(decision_request)
        if not decision.requires_cancel_rebook:
            raise ValueError("The requested changes are not eligible for cancel and rebook")
        self._require_unique_reference(request.replacement_reference)
        original_message = self._original_instruction(request.original_instruction_id)
        original_before = original_message.scenario.model_dump(mode="json", by_alias=True)
        cancellation = self.cancellation(
            SettlementCancellationRequest(
                original_instruction_id=request.original_instruction_id,
                cancellation_reference=request.cancellation_reference,
            )
        )
        cancellation_status = self._lifecycle.generate_response(
            cancellation.message_id,
            LifecycleResponseRequest(
                action=ResponseAction.CANCELLATION_ACCEPTED_STATUS,
                reason_code="CANCELLATION_PROCESSED",
            ),
        )
        replacement = original_message.scenario.model_copy(
            deep=True,
            update={
                "scenario_id": f"{original_message.scenario.scenario_id}-REBOOK",
                "function": MessageFunction.NEWM,
                "sender_reference": request.replacement_reference,
                "related_reference": original_message.scenario.sender_reference,
                "test_configuration": TestConfiguration(),
            },
        )
        for change in request.changes:
            self._apply_core_change(replacement, change)
        generated_replacement = self._generation.generate(
            replacement,
            related_message_id=request.original_instruction_id,
        )
        original_after = self._messages.get(request.original_instruction_id).scenario.model_dump(
            mode="json", by_alias=True
        )
        if original_after != original_before:
            raise RuntimeError("Original instruction immutability check failed")
        return CancelRebookResponse(
            decision=decision,
            cancellation=cancellation,
            cancellation_status=cancellation_status,
            replacement=generated_replacement,
            before_values=self._selected_values(original_message.scenario, request.changes),
            after_values=self._selected_values(replacement, request.changes),
        )

    def _original_instruction(self, message_id: str) -> GeneratedMessage:
        message = self._messages.get(message_id)
        if (
            message.scenario.lifecycle != Lifecycle.INSTRUCTION
            or message.resolved_message_type not in SUPPORTED_INSTRUCTIONS
            or message.scenario.function == MessageFunction.CANC
        ):
            raise ValueError("A persisted original MT540–MT543 instruction is required")
        return message

    def _decision(
        self,
        original: SettlementScenario,
        changes: list[AmendmentChange],
        classification: AmendmentClassification,
        method: str,
        explanation: str,
    ) -> AmendmentDecisionResponse:
        profile = self._profiles.get(original.profile_id)
        return AmendmentDecisionResponse(
            classification=classification,
            method=method,
            explanation=explanation,
            direct_amendment_supported=(method == "MT530_PRIORITY"),
            requires_cancel_rebook=(method == "CANCEL_REBOOK"),
            affected_fields=[item.field_path for item in changes],
            source_reference=self._policy.source.source_reference,
            profile_id=profile.profile_id,
            profile_version=profile.version,
        )

    def _require_unique_reference(self, reference: str) -> None:
        if self._messages.sender_reference_exists(reference):
            raise ValueError("The new sender reference must be unique")

    @staticmethod
    def _apply_core_change(scenario: SettlementScenario, change: AmendmentChange) -> None:
        if change.proposed_value is None:
            raise ValueError(f"A proposed value is required for {change.field_path.value}")
        value = change.proposed_value
        try:
            if change.field_path == AmendmentField.QUANTITY:
                scenario.security.quantity = Decimal(value)
            elif change.field_path == AmendmentField.SECURITY_IDENTIFIER:
                scenario.security.identifier = value
            elif change.field_path == AmendmentField.SETTLEMENT_AMOUNT:
                scenario.settlement.amount = Decimal(value)
            elif change.field_path == AmendmentField.SETTLEMENT_DATE:
                scenario.trade.settlement_date = date.fromisoformat(value)
            elif change.field_path == AmendmentField.SAFEKEEPING_ACCOUNT:
                scenario.account.safekeeping_account = value
            else:
                raise ValueError(
                    "Structured cancel-and-rebook input is not supported for "
                    f"{change.field_path.value}"
                )
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid proposed value for {change.field_path.value}") from exc

    @staticmethod
    def _selected_values(
        scenario: SettlementScenario, changes: list[AmendmentChange]
    ) -> dict[str, Any]:
        payload = scenario.model_dump(mode="json", by_alias=True)
        selected: dict[str, Any] = {}
        for change in changes:
            current: Any = payload
            for part in change.field_path.value.split("."):
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(part)
            selected[change.field_path.value] = current
        return selected

    @staticmethod
    def _reference(prefix: str) -> str:
        return f"{prefix}{uuid4().hex[:10].upper()}"


settlement_amendment_policy = load_amendment_policy()
