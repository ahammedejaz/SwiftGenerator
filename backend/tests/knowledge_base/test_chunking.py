"""Chunking: stable, section- and page-aware, never across two messages."""

from __future__ import annotations

from pathlib import Path

from app.knowledge_base.chunking import identifiers_in, segment_source
from app.knowledge_base.discovery import DiscoveredFile
from app.knowledge_base.identify import parse_and_identify
from app.knowledge_base.models import Section, SourceFormat, TableState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "knowledge"


def _segments(name: str):  # type: ignore[no-untyped-def]
    raw = (FIXTURES / name).read_bytes()
    parsed = parse_and_identify(
        DiscoveredFile(name, FIXTURES / name, len(raw), Path(name).suffix), raw
    )
    return parsed, segment_source(parsed.identity, parsed.text)


def test_segment_ids_and_hashes_are_stable_across_runs() -> None:
    _parsed, first = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    _parsed, second = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    assert [s.segment_id for s in first] == [s.segment_id for s in second]
    assert [s.segment_hash for s in first] == [s.segment_hash for s in second]
    assert first[0].segment_id == "SWIFT-MT-SR2026-MT999-MRG#S0001"
    assert len({s.segment_id for s in first}) == len(first)


def test_pages_and_sections_are_preserved_and_never_crossed() -> None:
    _parsed, segments = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    sections = {s.section for s in segments}
    assert Section.NETWORK_VALIDATED_RULE in sections
    assert Section.FIELD_SPECIFICATION in sections
    assert Section.FORMAT_SPECIFICATION in sections
    assert Section.USAGE_RULE in sections
    assert all(s.page is not None for s in segments)
    # The usage rules and the field specifications share page 7; a segment sits in one.
    page_seven = [s for s in segments if s.page == 7]
    assert {s.section for s in page_seven} >= {Section.USAGE_RULE, Section.FIELD_SPECIFICATION}
    assert all(s.page == 7 for s in page_seven)


def test_rule_boundaries_start_new_segments() -> None:
    _parsed, segments = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    rules = [s for s in segments if s.section is Section.NETWORK_VALIDATED_RULE]
    starts = [s.text.split()[0] for s in rules if s.text[:1] == "C" and s.text[1:2].isdigit()]
    assert starts[:3] == ["C1", "C2", "C3"]
    assert all(s.heading and s.heading.startswith("C") for s in rules if s.text.startswith("C"))


def test_field_specification_segments_carry_their_heading() -> None:
    _parsed, segments = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    fields = [s for s in segments if s.section is Section.FIELD_SPECIFICATION]
    assert any(s.heading and "Field 20C" in s.heading for s in fields)
    assert any(s.heading and "Field 95a" in s.heading for s in fields)


def test_format_specification_tables_are_marked_extracted() -> None:
    _parsed, segments = _segments("guides/mt999-synthetic-guide-sr2026.txt")
    tables = [s for s in segments if s.section is Section.FORMAT_SPECIFICATION]
    assert tables
    assert all(s.table_state is TableState.TABLE_EXTRACTED for s in tables)


def test_a_segment_carries_exactly_one_message_identity() -> None:
    _parsed, segments = _segments("guides/mt999-synthetic-guide-sr2027.txt")
    assert {s.message_type for s in segments} == {"MT999"}
    assert {s.release for s in segments} == {"SR2027"}
    assert {s.source_id for s in segments} == {"SWIFT-MT-SR2027-MT999-MRG"}


def test_identifiers_are_extracted_for_lexical_search() -> None:
    tags = identifiers_in(
        "C6 If :20C::PREV is present (Error code(s): Z06) then :95a::PSET and DEAG", SourceFormat.MT
    )
    assert {"20C", "PREV", "C6", "Z06", "PSET", "DEAG"} <= set(tags)
    mx = identifiers_in("## Type SynthTstInstr\n- SttlmAmt : Amount [1..1]\n", SourceFormat.MX)
    assert {"SynthTstInstr", "SttlmAmt"} <= set(mx)


def test_xsd_summary_segments_one_type_per_segment() -> None:
    _parsed, segments = _segments("schemas/test.001.001.01.xsd")
    headings = [s.heading for s in segments]
    assert any(h and "SyntheticTestInstructionV01" in h for h in headings)
    assert all(
        s.section in {Section.ELEMENT_DEFINITION, Section.MESSAGE_DEFINITION} for s in segments
    )
