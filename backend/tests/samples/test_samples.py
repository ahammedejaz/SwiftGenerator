from app.domain.enums import MessageType
from app.samples.service import sample_service
from app.specifications.registry import specification_registry


def test_every_target_message_has_composer_generated_annotated_sample() -> None:
    summaries = sample_service.list()
    assert {item.message_type for item in summaries} == set(MessageType)
    for summary in summaries:
        detail = sample_service.get(summary.sample_id)
        assert detail.synthetic is True
        assert detail.generated_by_production_composer is True
        assert detail.annotations
        assert detail.raw_message.startswith("{1:DEMONSTRATION}")
        assert all(item.source.value == "SAMPLE_DATA" for item in detail.annotations)
        specification = specification_registry.get(summary.message_type)
        configured_rows = {item.row_id for item in specification.fields}
        assert set(detail.covered_row_ids).issubset(configured_rows)


def test_sample_annotations_are_exactly_linked_to_knowledge() -> None:
    detail = sample_service.get("MT541-SYNTHETIC-V1")
    assert any(item.qualifier == "PSET" for item in detail.annotations)
    assert all(item.business_meaning and item.why_used for item in detail.annotations)
    assert len(detail.annotations) == len(detail.covered_row_ids)
