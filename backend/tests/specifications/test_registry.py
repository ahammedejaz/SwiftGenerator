from app.domain.enums import MessageType
from app.specifications.models import CapabilityState, VerificationStatus
from app.specifications.registry import specification_registry

EXPECTED_ROWS = {
    MessageType.MT530: 5,
    MessageType.MT537: 23,
    MessageType.MT540: 14,
    MessageType.MT541: 15,
    MessageType.MT542: 14,
    MessageType.MT543: 15,
    MessageType.MT544: 12,
    MessageType.MT545: 13,
    MessageType.MT546: 12,
    MessageType.MT547: 13,
    MessageType.MT548: 12,
    MessageType.MT564: 14,
    MessageType.MT565: 10,
    MessageType.MT566: 13,
    MessageType.MT567: 9,
    MessageType.MT568: 6,
}


def test_registry_accounts_for_the_source_bounded_subset() -> None:
    assert specification_registry.statistics() == {
        item.value: count for item, count in EXPECTED_ROWS.items()
    }
    assert sum(EXPECTED_ROWS.values()) == 200
    for message_type, expected in EXPECTED_ROWS.items():
        specification = specification_registry.get(message_type)
        assert len(specification.fields) == expected
        assert specification.capability is CapabilityState.PARTIAL
        assert specification.authoritative_completeness_known is False
        assert all(
            row.source.verification_status is VerificationStatus.EXTERNAL_VALIDATION_REQUIRED
            for row in specification.fields
        )


def test_registry_has_unique_rows_and_resolved_sequence_references() -> None:
    for specification in specification_registry.list():
        row_ids = [row.row_id for row in specification.fields]
        assert len(row_ids) == len(set(row_ids))
        paths = {sequence.path for sequence in specification.sequences}
        assert all(row.sequence_path in paths for row in specification.fields)


def test_coverage_gate_cannot_pass_without_authoritative_denominator() -> None:
    coverage = specification_registry.coverage(MessageType.MT541)
    assert coverage.configured_format_rows == EXPECTED_ROWS[MessageType.MT541]
    assert coverage.knowledge_records.percentage == 100
    assert coverage.production_gate_passed is False
    assert coverage.authoritative_completeness_known is False


def test_catalogue_only_messages_cannot_be_generated() -> None:
    catalogue = specification_registry.catalogue()
    assert {message.message_type for message in catalogue.catalogue_only} == {
        "MT535",
        "MT536",
        "MT538",
        "MT578",
    }
    assert all(
        message.capability is CapabilityState.CATALOGUE_ONLY
        and message.message == "Specification visible; generation not implemented."
        for message in catalogue.catalogue_only
    )
