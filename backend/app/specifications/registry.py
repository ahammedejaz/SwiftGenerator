from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.config import get_settings, source_path
from app.domain.enums import MessageType
from app.knowledge.loader import KNOWN_MESSAGE_OWNERS, knowledge_repository
from app.knowledge.models import PresenceRule
from app.raw.validator import FIELD_RANK
from app.specifications.models import (
    CapabilityState,
    CoverageMetric,
    CoverageReport,
    FieldSpecification,
    MessageCatalogue,
    MessageCoverage,
    MessageSpecification,
    SequenceSpecification,
    SpecificationManifest,
    SpecificationSource,
)


class MessageSpecificationRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or source_path(
            get_settings().mt_specification_manifest,
            "specifications",
            "supported_subset_v1.yaml",
        )
        self._manifest, self._messages = self._load()

    def _load(self) -> tuple[SpecificationManifest, dict[MessageType, MessageSpecification]]:
        with self._path.open(encoding="utf-8") as source:
            raw = yaml.safe_load(source)
        manifest = SpecificationManifest.model_validate(raw)
        messages: dict[MessageType, MessageSpecification] = {}
        for raw_message in manifest.messages:
            message_type = MessageType(str(raw_message["messageType"]))
            if message_type in messages:
                raise ValueError(f"Duplicate message specification: {message_type.value}")
            raw_sequences = raw_message.get("sequences")
            if not isinstance(raw_sequences, list) or not raw_sequences:
                raise ValueError(f"{message_type.value} must define sequences")
            sequences = [SequenceSpecification.model_validate(item) for item in raw_sequences]
            self._validate_sequences(message_type, sequences)
            by_path = {sequence.path: sequence for sequence in sequences}
            records = knowledge_repository.list_records(message_type=message_type)
            if not records:
                raise ValueError(f"{message_type.value} has no verified field records")
            fields: list[FieldSpecification] = []
            ordered_records = sorted(
                (effective.record for effective in records),
                key=lambda item: (
                    by_path[item.sequence_path].order,
                    FIELD_RANK.get(by_path[item.sequence_path].code, {}).get(
                        (item.field_tag, item.qualifier), 10_000
                    ),
                    item.knowledge_id,
                ),
            )
            for row_number, record in enumerate(ordered_records, start=1):
                sequence = by_path.get(record.sequence_path)
                if sequence is None:
                    raise ValueError(
                        f"{record.knowledge_id} references unknown sequence {record.sequence_path}"
                    )
                fields.append(
                    FieldSpecification(
                        row_id=record.knowledge_id,
                        row_number=row_number,
                        message_type=message_type,
                        workflow_module=record.workflow_module,
                        sequence_path=record.sequence_path,
                        sequence_code=sequence.code,
                        tag=record.field_tag,
                        option=record.field_tag[-1],
                        qualifier=record.qualifier,
                        business_path=record.business_path,
                        business_name=record.display_name,
                        technical_name=record.technical_meaning,
                        presence=record.presence,
                        min_occurs=1 if record.presence == PresenceRule.MANDATORY else 0,
                        max_occurs=1,
                        repeatable=False,
                        format=record.format_explanation,
                        allowed_options=record.supported_options,
                        allowed_codes=record.allowed_codes,
                        condition_expression=record.condition_expression,
                        condition_explanation=record.condition_explanation,
                        rule_layer=record.rule_layer,
                        knowledge_id=record.knowledge_id,
                        source=SpecificationSource(
                            source_type=record.source.source_type,
                            source_reference=record.source.source_reference,
                            standards_release=record.standards_release,
                            verification_status=manifest.source.verification_status,
                            verified_at=datetime.combine(
                                record.source.reviewed_at, datetime.min.time(), tzinfo=UTC
                            ),
                            verification_method=manifest.source.verification_method,
                        ),
                    )
                )
            messages[message_type] = MessageSpecification(
                message_type=message_type,
                name=str(raw_message["name"]),
                scope=str(raw_message["scope"]),
                capability=CapabilityState.PARTIAL,
                capability_explanation=(
                    "Configured source-bounded rows are implemented, but full current "
                    "authoritative format and client-rule completeness is not established."
                ),
                workflow_module=KNOWN_MESSAGE_OWNERS[message_type],
                standards_release=manifest.standards_release,
                registry_version=manifest.registry_version,
                authoritative_completeness_known=manifest.authoritative_completeness_known,
                sequences=sequences,
                fields=fields,
                source=manifest.source,
            )
        missing = set(MessageType) - set(messages)
        if missing:
            raise ValueError(
                "Target specifications are missing: "
                + ", ".join(sorted(item.value for item in missing))
            )
        return manifest, messages

    @staticmethod
    def _validate_sequences(
        message_type: MessageType, sequences: list[SequenceSpecification]
    ) -> None:
        paths = [item.path for item in sequences]
        codes = [item.code for item in sequences]
        if len(paths) != len(set(paths)) or len(codes) != len(set(codes)):
            raise ValueError(f"{message_type.value} sequence paths and codes must be unique")
        known = set(paths)
        orders = [item.order for item in sequences]
        if len(orders) != len(set(orders)):
            raise ValueError(f"{message_type.value} sequence orders must be unique")
        for sequence in sequences:
            if sequence.parent_path and sequence.parent_path not in known:
                raise ValueError(
                    f"{message_type.value} sequence {sequence.path} has unknown parent"
                )
            if sequence.min_occurs > sequence.max_occurs:
                raise ValueError(f"{message_type.value} sequence cardinality is invalid")

    @property
    def registry_version(self) -> str:
        return self._manifest.registry_version

    def list(self) -> list[MessageSpecification]:
        return [self._messages[item] for item in sorted(self._messages, key=lambda x: x.value)]

    def get(self, message_type: MessageType) -> MessageSpecification:
        return self._messages[message_type]

    def catalogue(self) -> MessageCatalogue:
        return MessageCatalogue(
            supported=self.list(),
            catalogue_only=self._manifest.catalogue_only,
            registry_version=self.registry_version,
        )

    def coverage(
        self,
        message_type: MessageType,
        *,
        sample_rows: set[str] | None = None,
        golden_rows: set[str] | None = None,
    ) -> MessageCoverage:
        specification = self.get(message_type)
        configured = len(specification.fields)

        def metric(count: int) -> CoverageMetric:
            return CoverageMetric(
                covered=count,
                configured=configured,
                percentage=round((count / configured * 100) if configured else 0, 2),
            )

        knowledge_count = len(knowledge_repository.list_records(message_type=message_type))
        form_count = sum(field.form_supported for field in specification.fields)
        composer_count = sum(field.composer_supported for field in specification.fields)
        parser_count = sum(field.parser_supported for field in specification.fields)
        validator_count = sum(field.validator_supported for field in specification.fields)
        sample_count = len(sample_rows or set())
        golden_count = len(golden_rows or set())
        gaps = [
            "Full current authoritative format-row denominator is unavailable.",
            "Current SR2026 network validation and client/market rules require authorised import.",
        ]
        return MessageCoverage(
            message_type=message_type,
            capability=specification.capability,
            authoritative_completeness_known=False,
            configured_format_rows=configured,
            knowledge_records=metric(knowledge_count),
            form_supported_fields=metric(form_count),
            composer_supported_fields=metric(composer_count),
            parser_supported_fields=metric(parser_count),
            validator_supported_fields=metric(validator_count),
            sample_covered_fields=metric(sample_count),
            golden_tested_fields=metric(golden_count),
            production_gate_passed=False,
            gaps=gaps,
        )

    def report(
        self,
        sample_coverage: dict[MessageType, set[str]] | None = None,
        golden_coverage: dict[MessageType, set[str]] | None = None,
    ) -> CoverageReport:
        sample_coverage = sample_coverage or {}
        golden_coverage = golden_coverage or {}
        messages = [
            self.coverage(
                message_type,
                sample_rows=sample_coverage.get(message_type),
                golden_rows=golden_coverage.get(message_type),
            )
            for message_type in sorted(self._messages, key=lambda item: item.value)
        ]
        return CoverageReport(
            registry_version=self.registry_version,
            generated_at=datetime.now(UTC),
            messages=messages,
            total_configured_rows=sum(item.configured_format_rows for item in messages),
            authoritative_completeness_known=False,
        )

    def statistics(self) -> dict[str, int]:
        return dict(
            Counter(field.message_type.value for item in self.list() for field in item.fields)
        )


specification_registry = MessageSpecificationRegistry()
