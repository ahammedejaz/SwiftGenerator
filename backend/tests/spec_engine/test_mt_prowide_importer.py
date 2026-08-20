from __future__ import annotations

from pathlib import Path

from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import SourceConfidence
from app.spec_engine.mt_prowide.reports import (
    COMPATIBILITY_DOCUMENT,
    STRUCTURE_DIFF_DOCUMENT,
    compare_controls,
    render_compatibility,
    render_structure_diff,
)
from app.specifications.registry import specification_registry


def test_fixture_covers_category5_without_activating_candidates() -> None:
    extraction = load_extraction()
    by_type = {message.message_type: message for message in extraction.messages}
    configured = {message.message_type for message in specification_registry.list()}

    assert len(extraction.messages) == 55
    assert configured <= set(by_type)
    assert len(extraction.candidate_messages) == 39
    assert extraction.activated_messages == []
    assert set(extraction.candidate_messages).isdisjoint(configured)
    assert all(
        not specification_registry.known(message_type)
        for message_type in extraction.candidate_messages
    )
    assert "MT541" in by_type
    assert {"GENL", "TRADDET", "FIAC", "SETDET"} <= {
        sequence.code for sequence in by_type["MT541"].sequences
    }


def test_global_field_definitions_are_separate_from_message_use() -> None:
    extraction = load_extraction()
    by_type = {message.message_type: message for message in extraction.messages}
    field20c = next(field for field in extraction.global_fields if field.tag == "20C")
    mt541_groups = [
        group for group in by_type["MT541"].field_groups if "20C" in group.tags
    ]

    assert field20c.validator_pattern == ":4!c//16x(***)"
    assert field20c.types_pattern == "SS"
    assert not hasattr(field20c, "presence")
    assert mt541_groups
    assert all(group.qualifier_legality == SourceConfidence.UNKNOWN for group in mt541_groups)
    assert all(
        group.code_list_legality == SourceConfidence.UNKNOWN for group in mt541_groups
    )


def test_configured_control_diff_reports_observed_and_missing_rows() -> None:
    comparisons = {item.message_type: item for item in compare_controls(load_extraction())}

    assert comparisons["MT530"].passed
    assert comparisons["MT537"].passed
    assert comparisons["MT541"].rows_observed_by_tag_and_sequence == 9
    assert comparisons["MT541"].missing_rows
    assert "MT541-E-19A-SETT" in comparisons["MT541"].missing_rows


def test_generated_reports_are_current() -> None:
    extraction = load_extraction()

    assert STRUCTURE_DIFF_DOCUMENT.read_text(encoding="utf-8") == render_structure_diff(
        extraction
    )
    assert COMPATIBILITY_DOCUMENT.read_text(encoding="utf-8") == render_compatibility(
        extraction
    )


def test_runtime_packages_do_not_import_build_time_prowide_tools() -> None:
    runtime_roots = [
        Path("app/api"),
        Path("app/authoring"),
        Path("app/bulk"),
        Path("app/composers"),
        Path("app/demo"),
        Path("app/domain"),
        Path("app/samples"),
        Path("app/studio"),
        Path("app/workflows"),
    ]
    hits: list[str] = []
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "app.spec_engine.mt_prowide" in text:
                hits.append(str(path))

    assert hits == []
