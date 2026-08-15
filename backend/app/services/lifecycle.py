from uuid import uuid4

from app.composers.base import MessageComposer
from app.composers.dvp_confirmation import DvpConfirmationComposer
from app.composers.fop_confirmation import FopConfirmationComposer
from app.composers.settlement_status import SettlementStatusComposer
from app.domain.enums import (
    GenerationMode,
    Lifecycle,
    MessageFunction,
    MessageType,
    PaymentType,
    ResponseAction,
    SettlementResult,
    Severity,
    StatusCategory,
    ValidationStatus,
)
from app.domain.models import (
    Confirmation,
    GeneratedMessage,
    LifecycleResponseRequest,
    SettlementScenario,
    StatusDetails,
    TestConfiguration,
    ValidationReport,
)
from app.domain.mutations import apply_negative_mutation
from app.domain.resolver import CONFIRMATION_TYPES
from app.domain.statuses import statuses
from app.domain.validation.engine import validate_scenario
from app.domain.validation.lifecycle import validate_lifecycle_response
from app.persistence.repository import MessageRepository
from app.profiles.loader import ProfileRepository
from app.services.generation import (
    DISCLAIMER,
    INTENTIONAL_INVALID_NOTICE,
    DomainValidationError,
)

STATUS_ACTIONS = {
    ResponseAction.PENDING_STATUS: StatusCategory.PENDING,
    ResponseAction.REJECTED_STATUS: StatusCategory.REJECTED,
    ResponseAction.MATCHED_STATUS: StatusCategory.MATCHED,
    ResponseAction.UNMATCHED_STATUS: StatusCategory.UNMATCHED,
    ResponseAction.CANCELLATION_ACCEPTED_STATUS: StatusCategory.CANCELLATION_ACCEPTED,
    ResponseAction.CANCELLATION_REJECTED_STATUS: StatusCategory.CANCELLATION_REJECTED,
}


class LifecycleService:
    def __init__(
        self,
        profile_repository: ProfileRepository,
        message_repository: MessageRepository,
    ) -> None:
        self._profiles = profile_repository
        self._messages = message_repository
        self._confirmation_composer = DvpConfirmationComposer()
        self._fop_confirmation_composer = FopConfirmationComposer()
        self._status_composer = SettlementStatusComposer()

    def generate_response(
        self,
        instruction_id: str,
        request: LifecycleResponseRequest,
    ) -> GeneratedMessage:
        instruction_message = self._messages.get(instruction_id)
        instruction = instruction_message.scenario
        if (
            instruction.message_type not in CONFIRMATION_TYPES
            or instruction.lifecycle != Lifecycle.INSTRUCTION
        ):
            raise ValueError("Responses must start from a supported settlement instruction")
        assert instruction.message_type is not None

        if request.action in STATUS_ACTIONS:
            response = self._build_status(instruction, request)
        else:
            response = self._build_confirmation(instruction, request)

        profile = self._profiles.get(response.profile_id)
        response = profile.apply_defaults(response)
        report = self._merge_findings(
            validate_scenario(response, profile),
            validate_lifecycle_response(response, instruction),
        )
        intentional_notice: str | None = None
        if request.generation_mode == GenerationMode.NEGATIVE_TEST:
            mutation = request.negative_mutation
            if mutation is None:
                raise ValueError("A controlled mutation is required in negative-test mode")
            if mutation not in profile.enabled_negative_mutations:
                raise ValueError(f"Mutation {mutation.value} is not enabled by the profile")
            if report.status != ValidationStatus.VALID:
                raise DomainValidationError(report)
            negative_configuration = response.test_configuration.model_copy(
                update={"mode": GenerationMode.NEGATIVE_TEST, "mutation": mutation}
            )
            response = response.model_copy(update={"test_configuration": negative_configuration})
            response, expected_rules = apply_negative_mutation(response, mutation)
            mutated_report = self._merge_findings(
                validate_scenario(response, profile),
                validate_lifecycle_response(response, instruction),
            )
            expected_seen = False
            unexpected_errors = []
            marked_findings = []
            for finding in mutated_report.findings:
                if finding.rule_id in expected_rules:
                    expected_seen = True
                    marked_findings.append(finding.model_copy(update={"intentional": True}))
                else:
                    marked_findings.append(finding)
                    if finding.severity == Severity.ERROR:
                        unexpected_errors.append(finding)
            report = mutated_report.model_copy(
                update={
                    "findings": marked_findings,
                    "status": ValidationStatus.INTENTIONALLY_INVALID,
                }
            )
            if not expected_seen or unexpected_errors:
                raise DomainValidationError(report)
            intentional_notice = INTENTIONAL_INVALID_NOTICE
        elif report.status != ValidationStatus.VALID:
            raise DomainValidationError(report)

        if response.message_type == MessageType.MT548:
            composer: MessageComposer = self._status_composer
        elif response.message_type in {MessageType.MT545, MessageType.MT547}:
            composer = self._confirmation_composer
        else:
            composer = self._fop_confirmation_composer
        composed = composer.compose(response, profile)
        assert response.message_type is not None
        generated = GeneratedMessage(
            message_id=str(uuid4()),
            scenario=response,
            resolved_message_type=response.message_type,
            raw_message=composed.raw_message,
            field_map=composed.field_map,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            validation=report,
            disclaimer=DISCLAIMER,
            intentional_invalid_notice=intentional_notice,
        )
        self._messages.save(generated, related_message_id=instruction_id)
        return generated

    def _build_status(
        self,
        instruction: SettlementScenario,
        request: LifecycleResponseRequest,
    ) -> SettlementScenario:
        category = STATUS_ACTIONS[request.action]
        if not request.reason_code:
            raise ValueError("A controlled reasonCode is required for a status response")
        definition = statuses.get(category)
        if not statuses.validate_reason(category, request.reason_code):
            raise ValueError(f"Reason {request.reason_code} is not supported for {category.value}")
        response_reference = request.response_reference or self._synthetic_reference("ST")
        return instruction.model_copy(
            deep=True,
            update={
                "scenario_id": f"{instruction.scenario_id}-{category.value}",
                "lifecycle": Lifecycle.STATUS,
                "message_type": MessageType.MT548,
                "function": MessageFunction.NEWM,
                "sender_reference": response_reference,
                "related_reference": instruction.sender_reference,
                "confirmation": Confirmation(),
                "status": StatusDetails(
                    category=category,
                    code=definition.code,
                    reason_code=request.reason_code,
                    narrative=request.reason_narrative,
                    related_instruction_message_type=instruction.message_type,
                ),
                "test_configuration": TestConfiguration(mode=GenerationMode.VALID),
            },
        )

    def _build_confirmation(
        self,
        instruction: SettlementScenario,
        request: LifecycleResponseRequest,
    ) -> SettlementScenario:
        assert instruction.message_type is not None
        if request.action not in {
            ResponseAction.FULL_CONFIRMATION,
            ResponseAction.PARTIAL_CONFIRMATION,
        }:
            raise ValueError(f"Unsupported lifecycle response action: {request.action.value}")
        if request.actual_settlement_date is None:
            raise ValueError("actualSettlementDate is required for a confirmation")
        if request.action == ResponseAction.FULL_CONFIRMATION:
            result = SettlementResult.FULL
            settled_quantity = instruction.security.quantity
            settled_amount = instruction.settlement.amount
        else:
            result = SettlementResult.PARTIAL
            if request.settled_quantity is None:
                raise ValueError("settledQuantity is required for a partial confirmation")
            if (
                instruction.payment_type == PaymentType.AGAINST_PAYMENT
                and request.settled_amount is None
            ):
                raise ValueError(
                    "settledAmount is required for an Against Payment partial confirmation"
                )
            settled_quantity = request.settled_quantity
            settled_amount = (
                request.settled_amount
                if instruction.payment_type == PaymentType.AGAINST_PAYMENT
                else None
            )
            if instruction.security.quantity and settled_quantity >= instruction.security.quantity:
                raise ValueError(
                    "A partial confirmation quantity must be less than the instructed quantity"
                )
        response_reference = request.response_reference or self._synthetic_reference("CF")
        return instruction.model_copy(
            deep=True,
            update={
                "scenario_id": f"{instruction.scenario_id}-{result.value}",
                "lifecycle": Lifecycle.CONFIRMATION,
                "message_type": CONFIRMATION_TYPES[instruction.message_type],
                "function": MessageFunction.NEWM,
                "sender_reference": response_reference,
                "related_reference": instruction.sender_reference,
                "confirmation": Confirmation(
                    confirmation_reference=response_reference,
                    actual_settlement_date=request.actual_settlement_date,
                    settled_quantity=settled_quantity,
                    settled_amount=settled_amount,
                    settlement_result=result,
                ),
                "status": StatusDetails(),
                "test_configuration": TestConfiguration(mode=GenerationMode.VALID),
            },
        )

    def _merge_findings(self, report: ValidationReport, findings):  # type: ignore[no-untyped-def]
        combined = [*report.findings, *findings]
        error_count = sum(item.severity == Severity.ERROR for item in combined)
        warning_count = sum(item.severity == Severity.WARNING for item in combined)
        return report.model_copy(
            update={
                "findings": combined,
                "error_count": error_count,
                "warning_count": warning_count,
                "status": ValidationStatus.INVALID if error_count else ValidationStatus.VALID,
            }
        )

    @staticmethod
    def _synthetic_reference(prefix: str) -> str:
        return f"{prefix}{uuid4().hex[:10].upper()}"
