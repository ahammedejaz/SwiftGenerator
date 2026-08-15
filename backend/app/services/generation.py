from uuid import uuid4

from app.composers.dvp_instruction import DvpInstructionComposer
from app.composers.fop_instruction import FopInstructionComposer
from app.domain.enums import GenerationMode, MessageType, Severity, ValidationStatus
from app.domain.models import (
    GeneratedMessage,
    MessageResolutionRequest,
    SettlementScenario,
    ValidationReport,
)
from app.domain.mutations import apply_negative_mutation
from app.domain.resolver import resolve_message_type
from app.domain.validation.engine import validate_scenario
from app.persistence.repository import MessageRepository
from app.profiles.loader import ProfileRepository

DISCLAIMER = (
    "Messages are generated against the selected source-bounded configured profile. "
    "They are not transmitted through or certified by the Swift network. Production "
    "submission requires authorised standards, market and institution rule packs, "
    "external validation, approval, and a contracted connector."
)
INTENTIONAL_INVALID_NOTICE = "Intentionally invalid message generated for negative testing."


class DomainValidationError(Exception):
    def __init__(self, report: ValidationReport) -> None:
        super().__init__("Scenario validation failed")
        self.report = report


class GenerationService:
    def __init__(
        self,
        profile_repository: ProfileRepository,
        message_repository: MessageRepository | None = None,
    ) -> None:
        self._profiles = profile_repository
        self._messages = message_repository
        self._mt541_composer = DvpInstructionComposer()
        self._fop_instruction_composer = FopInstructionComposer()

    def prepare(self, scenario: SettlementScenario) -> SettlementScenario:
        profile = self._profiles.get(scenario.profile_id)
        prepared = profile.apply_defaults(scenario)
        if prepared.message_type is None:
            resolution = resolve_message_type(
                MessageResolutionRequest(
                    lifecycle=prepared.lifecycle,
                    direction=prepared.direction,
                    payment_type=prepared.payment_type,
                )
            )
            if resolution.resolved_message_type:
                prepared = prepared.model_copy(
                    update={"message_type": resolution.resolved_message_type}
                )
        return prepared

    def validate(self, scenario: SettlementScenario) -> tuple[SettlementScenario, ValidationReport]:
        prepared = self.prepare(scenario)
        profile = self._profiles.get(prepared.profile_id)
        return prepared, validate_scenario(prepared, profile)

    def generate(
        self,
        scenario: SettlementScenario,
        *,
        related_message_id: str | None = None,
    ) -> GeneratedMessage:
        prepared = self.prepare(scenario)
        profile = self._profiles.get(prepared.profile_id)
        intentional_notice: str | None = None
        if prepared.test_configuration.mode == GenerationMode.VALID:
            report = validate_scenario(prepared, profile)
            if report.status != ValidationStatus.VALID:
                raise DomainValidationError(report)
        else:
            mutation = prepared.test_configuration.mutation
            if mutation is None:
                raise ValueError("A controlled mutation is required in negative-test mode")
            if mutation not in profile.enabled_negative_mutations:
                raise ValueError(
                    f"Mutation {mutation.value} is not enabled by profile {profile.profile_id}"
                )
            baseline_configuration = prepared.test_configuration.model_copy(
                update={"mode": GenerationMode.VALID, "mutation": None}
            )
            baseline = prepared.model_copy(update={"test_configuration": baseline_configuration})
            baseline_report = validate_scenario(baseline, profile)
            if baseline_report.status != ValidationStatus.VALID:
                raise DomainValidationError(baseline_report)
            prepared, expected_rules = apply_negative_mutation(prepared, mutation)
            mutated_report = validate_scenario(prepared, profile)
            expected_seen = False
            findings = []
            unexpected_errors = []
            for finding in mutated_report.findings:
                if finding.rule_id in expected_rules:
                    expected_seen = True
                    findings.append(finding.model_copy(update={"intentional": True}))
                else:
                    findings.append(finding)
                    if finding.severity == Severity.ERROR:
                        unexpected_errors.append(finding)
            report = mutated_report.model_copy(
                update={
                    "findings": findings,
                    "status": ValidationStatus.INTENTIONALLY_INVALID,
                }
            )
            if not expected_seen or unexpected_errors:
                raise DomainValidationError(report)
            intentional_notice = INTENTIONAL_INVALID_NOTICE
        if prepared.message_type in {MessageType.MT540, MessageType.MT542}:
            composed = self._fop_instruction_composer.compose(prepared, profile)
        elif prepared.message_type in {MessageType.MT541, MessageType.MT543}:
            composed = self._mt541_composer.compose(prepared, profile)
        else:
            raise ValueError(
                "Generate confirmations and statuses from a persisted instruction response action"
            )
        generated = GeneratedMessage(
            message_id=str(uuid4()),
            scenario=prepared,
            resolved_message_type=prepared.message_type,
            raw_message=composed.raw_message,
            field_map=composed.field_map,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            validation=report,
            disclaimer=DISCLAIMER,
            intentional_invalid_notice=intentional_notice,
        )
        if self._messages:
            self._messages.save(generated, related_message_id=related_message_id)
        return generated
