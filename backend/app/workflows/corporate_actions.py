from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from app.domain.enums import (
    CorporateActionClassification,
    CorporateActionEventType,
    CorporateActionInstructionStatus,
    CorporateActionNarrativeCategory,
    CorporateActionOptionCode,
    MessageType,
    ValidationStatus,
)
from app.domain.models import ApiModel, ValidationReport
from app.knowledge.models import WorkflowModuleId
from app.persistence.workflow_messages import WorkflowMessageRepository
from app.profiles.loader import ProfileRepository
from app.workflows.models import WorkflowGeneratedMessage

REFERENCE_PATTERN = re.compile(r"^(?!/)(?!.*//)[A-Z0-9._-]{1,16}(?<!/)$")
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
NARRATIVE_PATTERN = re.compile(r"^[A-Z0-9 .,'()+/:?=\-\n]{1,350}$")


class CorporateActionOption(ApiModel):
    option_number: int = Field(ge=1, le=999)
    option_code: CorporateActionOptionCode
    default_option: bool = False


class CorporateActionNotification(ApiModel):
    workflow_id: str = Field(min_length=3, max_length=64)
    profile_id: str = "BASE_DEMO_V1"
    event_reference: str
    message_reference: str
    event_type: CorporateActionEventType = CorporateActionEventType.DIVIDEND_WITH_OPTIONS
    classification: CorporateActionClassification = CorporateActionClassification.VOLUNTARY
    security_identifier: str
    safekeeping_account: str = Field(min_length=3, max_length=35)
    eligible_quantity: Decimal = Field(gt=0)
    election_deadline: date
    payment_date: date
    options: list[CorporateActionOption] = Field(min_length=2, max_length=9)
    synthetic_data: bool = True

    @field_validator("event_reference", "message_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value

    @field_validator("security_identifier")
    @classmethod
    def validate_security_identifier(cls, value: str) -> str:
        if not ISIN_PATTERN.fullmatch(value):
            raise ValueError("Security identifier must use the supported synthetic ISIN shape")
        return value

    @model_validator(mode="after")
    def validate_notification(self) -> CorporateActionNotification:
        if not self.synthetic_data:
            raise ValueError("Only synthetic corporate-action data is supported")
        option_numbers = [item.option_number for item in self.options]
        if len(option_numbers) != len(set(option_numbers)):
            raise ValueError("Corporate-action option numbers must be unique")
        if sum(item.default_option for item in self.options) != 1:
            raise ValueError("Exactly one corporate-action option must be the default")
        if self.payment_date < self.election_deadline:
            raise ValueError("Payment date must not precede the election deadline")
        return self


class CorporateActionNotificationRequest(ApiModel):
    notification: CorporateActionNotification


class CorporateActionInstructionRequest(ApiModel):
    workflow_id: str
    profile_id: str = "BASE_DEMO_V1"
    message_reference: str
    notification_message_id: str
    option_number: int = Field(ge=1, le=999)
    instructed_quantity: Decimal = Field(gt=0)
    cancellation: bool = False

    @field_validator("message_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value


class CorporateActionStatusRequest(ApiModel):
    workflow_id: str
    profile_id: str = "BASE_DEMO_V1"
    message_reference: str
    instruction_message_id: str
    status: CorporateActionInstructionStatus
    reason_code: str | None = Field(default=None, pattern=r"^[A-Z0-9]{4}$")

    @field_validator("message_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value


class CorporateActionConfirmationRequest(ApiModel):
    workflow_id: str
    profile_id: str = "BASE_DEMO_V1"
    message_reference: str
    instruction_message_id: str
    option_number: int = Field(ge=1, le=999)
    confirmed_quantity: Decimal = Field(gt=0)
    cash_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    cash_amount: Decimal | None = Field(default=None, gt=0)
    payment_date: date | None = None

    @field_validator("message_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value


class CorporateActionNarrativeRequest(ApiModel):
    workflow_id: str
    profile_id: str = "BASE_DEMO_V1"
    message_reference: str
    notification_message_id: str
    category: CorporateActionNarrativeCategory = CorporateActionNarrativeCategory.ADDITIONAL_TEXT
    narrative: str

    @field_validator("message_reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        if not REFERENCE_PATTERN.fullmatch(value):
            raise ValueError("References use the supported 1–16 character subset")
        return value

    @field_validator("narrative")
    @classmethod
    def validate_narrative(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").upper()
        if not NARRATIVE_PATTERN.fullmatch(normalized):
            raise ValueError("Narrative contains unsupported or control characters")
        if any(token in normalized for token in ("<SCRIPT", "```", "{1:", ":20C:")):
            raise ValueError("Narrative must not contain code or raw-message fragments")
        return normalized


class CorporateActionWorkflowService:
    def __init__(
        self,
        profiles: ProfileRepository,
        workflows: WorkflowMessageRepository,
    ) -> None:
        self._profiles = profiles
        self._workflows = workflows

    def notification(self, request: CorporateActionNotificationRequest) -> WorkflowGeneratedMessage:
        from app.composers.corporate_actions import CorporateActionComposer

        notification = request.notification
        profile = self._profiles.get(notification.profile_id)
        self._require_enabled(profile.supported_message_types, MessageType.MT564)
        if self._workflows.reference_exists(notification.event_reference):
            raise ValueError("Corporate-action event reference already exists")
        if self._workflows.reference_exists(notification.message_reference):
            raise ValueError("Corporate-action message reference already exists")
        generated = self._generated(
            notification.workflow_id,
            MessageType.MT564,
            notification.model_dump(mode="json", by_alias=True)
            | {"businessStatus": "Notification"},
            CorporateActionComposer().notification(notification),
            notification.profile_id,
        )
        self._workflows.save(generated)
        return generated

    def instruction(self, request: CorporateActionInstructionRequest) -> WorkflowGeneratedMessage:
        from app.composers.corporate_actions import CorporateActionComposer

        notification_message, notification = self._notification_context(
            request.notification_message_id, request.workflow_id
        )
        self._require_reference_unique(request.message_reference)
        if request.profile_id != notification.profile_id:
            raise ValueError("Instruction profile must match the notification profile")
        if request.cancellation:
            raise ValueError(
                "MT565 cancellation is outside the verified first corporate-action slice"
            )
        option = self._option(notification, request.option_number)
        if request.instructed_quantity > notification.eligible_quantity:
            raise ValueError("Instructed quantity exceeds the eligible quantity")
        if date.today() > notification.election_deadline:
            raise ValueError("The configured election deadline has passed")
        profile = self._profiles.get(request.profile_id)
        self._require_enabled(profile.supported_message_types, MessageType.MT565)
        canonical = request.model_dump(mode="json", by_alias=True) | {
            "eventReference": notification.event_reference,
            "notificationReference": notification.message_reference,
            "securityIdentifier": notification.security_identifier,
            "safekeepingAccount": notification.safekeeping_account,
            "optionCode": option.option_code.value,
            "businessStatus": "Election",
        }
        generated = self._generated(
            request.workflow_id,
            MessageType.MT565,
            canonical,
            CorporateActionComposer().instruction(request, notification, option),
            request.profile_id,
            related_workflow_message_id=notification_message.message_id,
        )
        self._workflows.save(generated)
        return generated

    def status(self, request: CorporateActionStatusRequest) -> WorkflowGeneratedMessage:
        from app.composers.corporate_actions import CorporateActionComposer

        instruction, notification, _ = self._instruction_context(
            request.instruction_message_id, request.workflow_id
        )
        self._require_reference_unique(request.message_reference)
        if request.profile_id != instruction.profile_id:
            raise ValueError("Status profile must match the instruction profile")
        cancellation_statuses = {
            CorporateActionInstructionStatus.CANCELLATION_ACKNOWLEDGED,
            CorporateActionInstructionStatus.CANCELLATION_REJECTED,
        }
        if request.status in cancellation_statuses and not instruction.canonical_data.get(
            "cancellation", False
        ):
            raise ValueError("Cancellation status requires a cancellation instruction")
        if (
            request.status
            in {
                CorporateActionInstructionStatus.REJECTED,
                CorporateActionInstructionStatus.CANCELLATION_REJECTED,
            }
            and not request.reason_code
        ):
            raise ValueError("A controlled four-character reason is required for rejection")
        profile = self._profiles.get(request.profile_id)
        self._require_enabled(profile.supported_message_types, MessageType.MT567)
        canonical = request.model_dump(mode="json", by_alias=True) | {
            "eventReference": notification.event_reference,
            "instructionReference": instruction.canonical_data["messageReference"],
            "businessStatus": request.status.value.replace("_", " ").title(),
        }
        generated = self._generated(
            request.workflow_id,
            MessageType.MT567,
            canonical,
            CorporateActionComposer().status(request, notification, instruction),
            request.profile_id,
            related_workflow_message_id=instruction.message_id,
        )
        self._workflows.save(generated)
        return generated

    def confirmation(self, request: CorporateActionConfirmationRequest) -> WorkflowGeneratedMessage:
        from app.composers.corporate_actions import CorporateActionComposer

        instruction, notification, option = self._instruction_context(
            request.instruction_message_id, request.workflow_id
        )
        self._require_reference_unique(request.message_reference)
        if request.profile_id != instruction.profile_id:
            raise ValueError("Confirmation profile must match the instruction profile")
        if request.option_number != instruction.canonical_data["optionNumber"]:
            raise ValueError("Confirmation option must match the instructed option")
        instructed = Decimal(str(instruction.canonical_data["instructedQuantity"]))
        if request.confirmed_quantity > instructed:
            raise ValueError("Confirmed quantity exceeds the instructed quantity")
        has_cash = any(
            value is not None
            for value in (request.cash_currency, request.cash_amount, request.payment_date)
        )
        if option.option_code == CorporateActionOptionCode.CASH:
            if not all(
                value is not None
                for value in (request.cash_currency, request.cash_amount, request.payment_date)
            ):
                raise ValueError("Cash confirmation requires currency, amount, and payment date")
            profile = self._profiles.get(request.profile_id)
            if request.cash_currency not in profile.allowed_currencies:
                raise ValueError("Cash currency is not allowed by the selected profile")
        elif has_cash:
            raise ValueError("Securities option confirmation must not contain cash movement")
        else:
            raise ValueError(
                "Securities-movement confirmation is not enabled in the verified first slice"
            )
        profile = self._profiles.get(request.profile_id)
        self._require_enabled(profile.supported_message_types, MessageType.MT566)
        canonical = request.model_dump(mode="json", by_alias=True) | {
            "eventReference": notification.event_reference,
            "instructionReference": instruction.canonical_data["messageReference"],
            "optionCode": option.option_code.value,
            "securityIdentifier": notification.security_identifier,
            "safekeepingAccount": notification.safekeeping_account,
            "eligibleQuantity": str(notification.eligible_quantity),
            "businessStatus": "Confirmation",
        }
        generated = self._generated(
            request.workflow_id,
            MessageType.MT566,
            canonical,
            CorporateActionComposer().confirmation(request, notification, option, instruction),
            request.profile_id,
            related_workflow_message_id=instruction.message_id,
        )
        self._workflows.save(generated)
        return generated

    def narrative(self, request: CorporateActionNarrativeRequest) -> WorkflowGeneratedMessage:
        from app.composers.corporate_actions import CorporateActionComposer

        notification_message, notification = self._notification_context(
            request.notification_message_id, request.workflow_id
        )
        self._require_reference_unique(request.message_reference)
        if request.profile_id != notification.profile_id:
            raise ValueError("Narrative profile must match the notification profile")
        profile = self._profiles.get(request.profile_id)
        self._require_enabled(profile.supported_message_types, MessageType.MT568)
        canonical = request.model_dump(mode="json", by_alias=True) | {
            "eventReference": notification.event_reference,
            "notificationReference": notification.message_reference,
            "businessStatus": "Narrative",
        }
        generated = self._generated(
            request.workflow_id,
            MessageType.MT568,
            canonical,
            CorporateActionComposer().narrative(request, notification),
            request.profile_id,
            related_workflow_message_id=notification_message.message_id,
        )
        self._workflows.save(generated)
        return generated

    def _notification_context(
        self, message_id: str, workflow_id: str
    ) -> tuple[WorkflowGeneratedMessage, CorporateActionNotification]:
        try:
            message = self._workflows.get(message_id)
        except KeyError as exc:
            raise ValueError("Corporate-action notification was not found") from exc
        if message.resolved_message_type != MessageType.MT564:
            raise ValueError("Related message is not an MT564 notification")
        if message.workflow_id != workflow_id:
            raise ValueError("Related message belongs to another workflow")
        source = dict(message.canonical_data)
        source.pop("businessStatus", None)
        return message, CorporateActionNotification.model_validate(source)

    def _instruction_context(
        self, message_id: str, workflow_id: str
    ) -> tuple[WorkflowGeneratedMessage, CorporateActionNotification, CorporateActionOption]:
        try:
            instruction = self._workflows.get(message_id)
        except KeyError as exc:
            raise ValueError("Corporate-action instruction was not found") from exc
        if instruction.resolved_message_type != MessageType.MT565:
            raise ValueError("Related message is not an MT565 instruction")
        notification, model = self._notification_context(
            str(instruction.related_workflow_message_id), workflow_id
        )
        return (
            instruction,
            model,
            self._option(model, int(instruction.canonical_data["optionNumber"])),
        )

    @staticmethod
    def _option(
        notification: CorporateActionNotification, option_number: int
    ) -> CorporateActionOption:
        for option in notification.options:
            if option.option_number == option_number:
                return option
        raise ValueError("Selected option is not offered by the notification")

    def _require_reference_unique(self, reference: str) -> None:
        if self._workflows.reference_exists(reference):
            raise ValueError("Corporate-action message reference already exists")

    @staticmethod
    def _require_enabled(supported: list[MessageType], message_type: MessageType) -> None:
        if message_type not in supported:
            raise ValueError(f"{message_type.value} is disabled by this profile")

    def _generated(
        self,
        workflow_id: str,
        message_type: MessageType,
        canonical_data: dict[str, object],
        composed: object,
        profile_id: str,
        related_workflow_message_id: str | None = None,
    ) -> WorkflowGeneratedMessage:
        from app.composers.base import CompositionResult

        assert isinstance(composed, CompositionResult)
        profile = self._profiles.get(profile_id)
        report = ValidationReport(
            status=ValidationStatus.VALID,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            findings=[],
            error_count=0,
            warning_count=0,
        )
        return WorkflowGeneratedMessage(
            message_id=str(uuid4()),
            workflow_id=workflow_id,
            workflow_module=WorkflowModuleId.CORPORATE_ACTIONS,
            resolved_message_type=message_type,
            canonical_data=canonical_data,
            raw_message=composed.raw_message,
            field_map=composed.field_map,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            validation=report,
            related_workflow_message_id=related_workflow_message_id,
        )
