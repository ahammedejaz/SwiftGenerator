from __future__ import annotations

from pathlib import Path

from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import (
    AuthoringReadinessStatus,
    CandidateStructureState,
    SourceConfidence,
)
from app.spec_engine.mt_prowide.references import resolve_field_reference
from app.spec_engine.mt_prowide.reports import (
    COMPATIBILITY_DOCUMENT,
    MULTICATEGORY_COVERAGE_DOCUMENT,
    STRUCTURE_DIFF_DOCUMENT,
    compare_controls,
    render_compatibility,
    render_multicategory_coverage,
    render_structure_diff,
)
from app.specifications.registry import specification_registry


def test_fixture_covers_all_discovered_categories_without_activating_candidates() -> None:
    extraction = load_extraction()
    by_type = {message.message_type: message for message in extraction.messages}
    configured = {message.message_type for message in specification_registry.list()}

    assert len(extraction.messages) == 274
    assert extraction.category_counts == {
        "0": 59,
        "1": 19,
        "2": 14,
        "3": 25,
        "4": 17,
        "5": 55,
        "6": 17,
        "7": 38,
        "8": 9,
        "9": 21,
    }
    assert extraction.discovered_categories == list(range(10))
    assert configured <= set(by_type)
    assert len(extraction.candidate_messages) == 258
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


def test_source_discovery_preserves_variants_and_non_category5_representatives() -> None:
    extraction = load_extraction()
    by_type = {message.message_type: message for message in extraction.messages}

    assert {"MT102_STP", "MT103_REMIT", "MT103_STP"} <= set(by_type)
    assert by_type["MT103_STP"].base_message_type == "MT103"
    assert by_type["MT103_STP"].variant == "STP"
    assert by_type["MT103_REMIT"].variant == "REMIT"
    assert by_type["MT202"].category == 2
    assert by_type["MT300"].category == 3
    assert by_type["MT400"].category == 4
    assert by_type["MT700"].category == 7
    assert by_type["MT940"].category == 9
    assert "MT202COV" not in by_type


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


def test_authoring_readiness_does_not_promote_source_models() -> None:
    extraction = load_extraction()
    by_type = {message.message_type: message for message in extraction.messages}

    assert by_type["MT541"].authoring_status == AuthoringReadinessStatus.PARTIAL
    assert CandidateStructureState.INSTALLED in by_type["MT541"].structure_states
    assert by_type["MT103"].authoring_status == (
        AuthoringReadinessStatus.STRUCTURAL_EVIDENCE_ONLY
    )
    assert by_type["MT103"].structure_states == [
        CandidateStructureState.SOURCE_DISCOVERED,
        CandidateStructureState.STRUCTURE_EXTRACTED,
    ]
    assert "NO_RUNTIME_SPECIFICATION" in by_type["MT103"].authoring_blockers
    assert not specification_registry.known("MT103")


def test_configured_control_diff_reports_observed_and_missing_rows() -> None:
    comparisons = {item.message_type: item for item in compare_controls(load_extraction())}

    assert comparisons["MT530"].passed
    assert comparisons["MT537"].passed
    assert comparisons["MT541"].rows_observed_by_tag_and_sequence == 9
    assert comparisons["MT541"].missing_rows
    assert "MT541-E-19A-SETT" in comparisons["MT541"].missing_rows
    assert {item.message_type for item in comparisons.values() if not item.passed} == {
        "MT540",
        "MT541",
        "MT542",
        "MT543",
        "MT544",
        "MT545",
        "MT546",
        "MT547",
        "MT548",
        "MT564",
    }
    assert {
        finding.classification
        for comparison in comparisons.values()
        for finding in comparison.missing_row_findings
    } == {
        "REPOSITORY_CONFIGURATION_DIFFERENCE",
        "SEQUENCE_DELIMITER_MATCHING_LIMITATION",
    }


def test_canonical_reference_resolver_addresses_message_context() -> None:
    reference = resolve_field_reference(
        load_extraction(),
        message_type="MT541",
        sequence_path="SETDET",
        tag="22F",
        qualifier="SETR",
    )

    assert reference.source_release == "SR2025"
    assert reference.message_type == "MT541"
    assert reference.source_model == "MT541"
    assert reference.sequence_path == "SETDET"
    assert reference.option == "F"
    assert reference.qualifier == "SETR"
    assert reference.canonical_id == "MT:SR2025:MT541:SETDET:22F:SETR"


def test_generated_reports_are_current() -> None:
    extraction = load_extraction()

    assert STRUCTURE_DIFF_DOCUMENT.read_text(encoding="utf-8") == render_structure_diff(
        extraction
    )
    assert COMPATIBILITY_DOCUMENT.read_text(encoding="utf-8") == render_compatibility(
        extraction
    )
    assert MULTICATEGORY_COVERAGE_DOCUMENT.read_text(
        encoding="utf-8"
    ) == render_multicategory_coverage(extraction)


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
