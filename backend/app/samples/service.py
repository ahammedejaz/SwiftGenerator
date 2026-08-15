from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.composers.base import CompositionResult
from app.composers.corporate_actions import CorporateActionComposer
from app.composers.dvp_confirmation import DvpConfirmationComposer
from app.composers.dvp_instruction import DvpInstructionComposer
from app.composers.fop_confirmation import FopConfirmationComposer
from app.composers.fop_instruction import FopInstructionComposer
from app.composers.penalty_statement import PenaltyStatementComposer
from app.composers.settlement_command import SettlementCommandComposer
from app.composers.settlement_status import SettlementStatusComposer
from app.domain.enums import (
    Direction,
    Lifecycle,
    MessageFunction,
    MessageType,
    PaymentType,
    SettlementCommandType,
    SettlementResult,
    StatusCategory,
    TransactionType,
)
from app.domain.models import (
    Account,
    Confirmation,
    Security,
    Settlement,
    SettlementCommandDetails,
    SettlementScenario,
    StatusDetails,
    Trade,
    ValidationReport,
)
from app.profiles.loader import profiles
from app.samples.models import AnnotatedSampleLine, SampleDetail, SampleSummary
from app.specifications.registry import specification_registry
from app.workflows.corporate_actions import (
    CorporateActionConfirmationRequest,
    CorporateActionInstructionRequest,
    CorporateActionNarrativeRequest,
    CorporateActionNotification,
    CorporateActionStatusRequest,
)
from app.workflows.models import WorkflowGeneratedMessage
from app.workflows.penalties import PenaltyStatement


class SampleService:
    def __init__(self) -> None:
        self._samples = self._build()

    def list(self) -> list[SampleSummary]:
        return [
            SampleSummary(
                sample_id=item.sample_id,
                message_type=item.message_type,
                scenario=item.scenario,
                profile_id=item.profile_id,
                profile_version=item.profile_version,
                standards_release=item.standards_release,
                capability=item.capability,
            )
            for item in sorted(self._samples.values(), key=lambda sample: sample.message_type.value)
        ]

    def get(self, sample_id: str) -> SampleDetail:
        try:
            return self._samples[sample_id]
        except KeyError as error:
            raise KeyError(sample_id) from error

    def coverage(self) -> dict[MessageType, set[str]]:
        return {item.message_type: set(item.covered_row_ids) for item in self._samples.values()}

    def _build(self) -> dict[str, SampleDetail]:
        compositions = _compositions()
        return {
            f"{message_type.value}-SYNTHETIC-V1": self._annotate(message_type, composed)
            for message_type, composed in compositions.items()
        }

    @staticmethod
    def _annotate(message_type: MessageType, composition: CompositionResult) -> SampleDetail:
        specification = specification_registry.get(message_type)
        lines = composition.raw_message.splitlines()
        cursor = 0
        annotations: list[AnnotatedSampleLine] = []
        covered: list[str] = []
        for rendered in composition.field_map:
            row = next(
                field
                for field in specification.fields
                if field.sequence_path == rendered.sequence
                and field.tag == rendered.tag
                and field.qualifier == rendered.qualifier
            )
            prefix = f":{rendered.tag}:"
            if rendered.qualifier:
                prefix += f":{rendered.qualifier}//"
            line_number = next(
                index for index in range(cursor, len(lines)) if lines[index].startswith(prefix)
            )
            cursor = line_number + 1
            from app.knowledge.loader import knowledge_repository

            knowledge = knowledge_repository.get(row.knowledge_id)
            annotations.append(
                AnnotatedSampleLine(
                    line_number=line_number + 1,
                    raw_line=lines[line_number],
                    sequence_path=rendered.sequence,
                    sequence_occurrence=sum(
                        1
                        for line in lines[: line_number + 1]
                        if line
                        == ":16R:"
                        + next(
                            sequence.code
                            for sequence in specification.sequences
                            if sequence.path == rendered.sequence
                        )
                    ),
                    row_id=row.row_id,
                    knowledge_id=row.knowledge_id,
                    tag=rendered.tag,
                    qualifier=rendered.qualifier,
                    entered_value=rendered.value,
                    business_meaning=knowledge.business_meaning,
                    why_used=knowledge.why_used,
                    presence=row.presence,
                )
            )
            covered.append(row.row_id)
        profile = profiles.get("BASE_DEMO_V1")
        return SampleDetail(
            sample_id=f"{message_type.value}-SYNTHETIC-V1",
            message_type=message_type,
            scenario=f"Synthetic configured-subset {message_type.value} golden path",
            profile_id=profile.profile_id,
            profile_version=profile.version,
            standards_release=specification.standards_release,
            capability=specification.capability,
            raw_message=composition.raw_message,
            annotations=annotations,
            covered_row_ids=list(dict.fromkeys(covered)),
            known_limitations=[
                "This sample covers the configured subset, not the complete current format.",
                "External and institution-specific validation has not been performed.",
            ],
        )


def _settlement_scenario(message_type: MessageType) -> SettlementScenario:
    instructions = {
        MessageType.MT540: (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT),
        MessageType.MT541: (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT),
        MessageType.MT542: (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT),
        MessageType.MT543: (Direction.DELIVER, PaymentType.AGAINST_PAYMENT),
    }
    confirmations = {
        MessageType.MT544: (Direction.RECEIVE, PaymentType.FREE_OF_PAYMENT),
        MessageType.MT545: (Direction.RECEIVE, PaymentType.AGAINST_PAYMENT),
        MessageType.MT546: (Direction.DELIVER, PaymentType.FREE_OF_PAYMENT),
        MessageType.MT547: (Direction.DELIVER, PaymentType.AGAINST_PAYMENT),
    }
    if message_type in instructions:
        direction, payment = instructions[message_type]
        return SettlementScenario(
            scenario_id=f"SAMPLE-{message_type.value}",
            lifecycle=Lifecycle.INSTRUCTION,
            direction=direction,
            payment_type=payment,
            message_type=message_type,
            function=MessageFunction.NEWM,
            sender_reference=f"SAMPLE{message_type.value[2:]}",
            trade=Trade(
                transaction_type=(
                    TransactionType.BUY if direction is Direction.RECEIVE else TransactionType.SELL
                ),
                trade_date=date(2026, 8, 3),
                settlement_date=date(2026, 8, 6),
            ),
            security=Security(identifier="XS0000000001", quantity=Decimal("1000")),
            account=Account(safekeeping_account="SAMPLESAFE01"),
            settlement=Settlement(
                currency="USD" if payment is PaymentType.AGAINST_PAYMENT else None,
                amount=Decimal("25000.00") if payment is PaymentType.AGAINST_PAYMENT else None,
                place_of_settlement="SAMPLEPSET01",
                delivering_agent="SAMPLEDEAG01",
                receiving_agent="SAMPLEREAG01",
            ),
        )
    if message_type in confirmations:
        direction, payment = confirmations[message_type]
        return SettlementScenario(
            scenario_id=f"SAMPLE-{message_type.value}",
            lifecycle=Lifecycle.CONFIRMATION,
            direction=direction,
            payment_type=payment,
            message_type=message_type,
            function=MessageFunction.NEWM,
            sender_reference=f"SAMPLE{message_type.value[2:]}",
            related_reference=f"SAMPLE{int(message_type.value[2:]) - 4}",
            security=Security(identifier="XS0000000001", quantity=Decimal("1000")),
            account=Account(safekeeping_account="SAMPLESAFE01"),
            settlement=Settlement(
                currency="USD" if payment is PaymentType.AGAINST_PAYMENT else None,
                amount=Decimal("25000.00") if payment is PaymentType.AGAINST_PAYMENT else None,
                place_of_settlement="SAMPLEPSET01",
                delivering_agent="SAMPLEDEAG01",
                receiving_agent="SAMPLEREAG01",
            ),
            confirmation=Confirmation(
                confirmation_reference=f"SAMPLE{message_type.value[2:]}",
                actual_settlement_date=date(2026, 8, 6),
                settled_quantity=Decimal("1000"),
                settled_amount=Decimal("25000.00")
                if payment is PaymentType.AGAINST_PAYMENT
                else None,
                settlement_result=SettlementResult.FULL,
            ),
        )
    return SettlementScenario(
        scenario_id="SAMPLE-MT548",
        lifecycle=Lifecycle.STATUS,
        direction=Direction.RECEIVE,
        payment_type=PaymentType.AGAINST_PAYMENT,
        message_type=MessageType.MT548,
        function=MessageFunction.NEWM,
        sender_reference="SAMPLE548",
        related_reference="SAMPLE541",
        status=StatusDetails(
            category=StatusCategory.PENDING,
            code="PEND",
            reason_code="AWAITING_CASH",
            narrative="SYNTHETIC SAMPLE PENDING STATUS",
            related_instruction_message_type=MessageType.MT541,
        ),
    )


def _corporate_action_compositions() -> dict[MessageType, CompositionResult]:
    notification = CorporateActionNotification.model_validate(
        {
            "workflowId": "CA-SAMPLE-WF",
            "eventReference": "CAEVENTSAMPLE01",
            "messageReference": "CA564SAMPLE001",
            "securityIdentifier": "XS0000000001",
            "safekeepingAccount": "SAMPLESAFE01",
            "eligibleQuantity": "1000",
            "electionDeadline": "2099-08-10",
            "paymentDate": "2099-08-15",
            "options": [
                {"optionNumber": 1, "optionCode": "CASH", "defaultOption": True},
                {
                    "optionNumber": 2,
                    "optionCode": "SECURITIES",
                    "defaultOption": False,
                },
            ],
        }
    )
    instruction = CorporateActionInstructionRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA565SAMPLE001",
            "notificationMessageId": "SAMPLE-NOTIFICATION-ID",
            "optionNumber": 1,
            "instructedQuantity": "800",
        }
    )
    report = ValidationReport.model_validate(
        {
            "status": "VALID",
            "profileId": "BASE_DEMO_V1",
            "profileVersion": "1.0.0",
            "findings": [],
            "errorCount": 0,
            "warningCount": 0,
        }
    )
    instruction_message = WorkflowGeneratedMessage.model_validate(
        {
            "messageId": "SAMPLE-INSTRUCTION-ID",
            "workflowId": notification.workflow_id,
            "workflowModule": "CORPORATE_ACTIONS",
            "resolvedMessageType": "MT565",
            "canonicalData": {"messageReference": instruction.message_reference},
            "rawMessage": "SYNTHETIC CONTEXT ONLY",
            "fieldMap": [],
            "profileId": "BASE_DEMO_V1",
            "profileVersion": "1.0.0",
            "validation": report,
        }
    )
    status = CorporateActionStatusRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA567SAMPLE001",
            "instructionMessageId": instruction_message.message_id,
            "status": "PENDING",
        }
    )
    confirmation = CorporateActionConfirmationRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA566SAMPLE001",
            "instructionMessageId": instruction_message.message_id,
            "optionNumber": 1,
            "confirmedQuantity": "800",
            "cashCurrency": "USD",
            "cashAmount": "125.50",
            "paymentDate": "2099-08-15",
        }
    )
    narrative = CorporateActionNarrativeRequest.model_validate(
        {
            "workflowId": notification.workflow_id,
            "messageReference": "CA568SAMPLE001",
            "notificationMessageId": "SAMPLE-NOTIFICATION-ID",
            "narrative": "SYNTHETIC SUPPORTING INFORMATION ONLY.",
        }
    )
    composer = CorporateActionComposer()
    return {
        MessageType.MT564: composer.notification(notification),
        MessageType.MT565: composer.instruction(instruction, notification, notification.options[0]),
        MessageType.MT566: composer.confirmation(
            confirmation, notification, notification.options[0], instruction_message
        ),
        MessageType.MT567: composer.status(status, notification, instruction_message),
        MessageType.MT568: composer.narrative(narrative, notification),
    }


def _compositions() -> dict[MessageType, CompositionResult]:
    profile = profiles.get("BASE_DEMO_V1")
    result: dict[MessageType, CompositionResult] = {}
    for message_type in (
        MessageType.MT540,
        MessageType.MT541,
        MessageType.MT542,
        MessageType.MT543,
    ):
        scenario = _settlement_scenario(message_type)
        instruction_composer = (
            FopInstructionComposer()
            if message_type in {MessageType.MT540, MessageType.MT542}
            else DvpInstructionComposer()
        )
        result[message_type] = instruction_composer.compose(scenario, profile)
    for message_type in (
        MessageType.MT544,
        MessageType.MT545,
        MessageType.MT546,
        MessageType.MT547,
    ):
        scenario = _settlement_scenario(message_type)
        confirmation_composer = (
            FopConfirmationComposer()
            if message_type in {MessageType.MT544, MessageType.MT546}
            else DvpConfirmationComposer()
        )
        result[message_type] = confirmation_composer.compose(scenario, profile)
    result[MessageType.MT548] = SettlementStatusComposer().compose(
        _settlement_scenario(MessageType.MT548), profile
    )
    command = SettlementScenario(
        scenario_id="SAMPLE-MT530",
        lifecycle=Lifecycle.INSTRUCTION,
        message_type=MessageType.MT530,
        function=MessageFunction.NEWM,
        sender_reference="COMMANDSAMPLE001",
        account=Account(safekeeping_account="SAMPLESAFE01"),
        command=SettlementCommandDetails(
            command_type=SettlementCommandType.MODIFY_PRIORITY,
            original_instruction_reference="ORIGSAMPLE00001",
            priority=42,
        ),
    )
    result[MessageType.MT530] = SettlementCommandComposer().compose(command, profile)
    penalty = PenaltyStatement.model_validate(
        {
            "workflowId": "PENALTY-SAMPLE-WF",
            "statementReference": "PENASAMPLE00001",
            "statementDate": "2026-08-05",
            "safekeepingAccount": "SAMPLESAFE01",
            "accountServicer": "SAMPLESERVICER",
            "relatedParty": "SAMPLEPARTY",
            "listType": "NEW_ONLY",
            "penalties": [
                {
                    "penaltyReference": "PENASAMPLE000001",
                    "commonReference": "COMMSAMPLE000001",
                    "relatedInstructionReference": "ORIGSAMPLE00001",
                    "penaltyType": "SETTLEMENT_FAIL",
                    "action": "NEW",
                    "status": "ACTIVE",
                    "currency": "EUR",
                    "amount": "25.00",
                    "amountDirection": "PAYABLE",
                    "detectionDate": "2026-08-04",
                    "numberOfDays": 1,
                }
            ],
        }
    )
    result[MessageType.MT537] = PenaltyStatementComposer().compose(penalty)
    result.update(_corporate_action_compositions())
    return result


sample_service = SampleService()
