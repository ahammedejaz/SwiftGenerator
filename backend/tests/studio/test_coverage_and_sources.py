"""The unified coverage report and the authoritative-source readiness report.

Two things are worth testing here and one is not. Worth testing: that the report covers
*every* configured message in both formats, and that its figures are measured from the real
components rather than declared — a report that reads a flag saying "the composer supports
this row" would have said 100% while the Excel reference sheet was quietly missing four
messages. Not worth testing: the exact numbers, which change whenever a YAML file does.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import MessageType
from app.specifications.registry import specification_registry
from app.studio.coverage import (
    CoverageBasis,
    RoundTrip,
    build_coverage,
    render_markdown,
)
from app.studio.models import MessageFormat
from app.studio.mx.registry import mx_registry
from app.studio.sources import SourceState, build_readiness

COVERAGE = build_coverage()


# --------------------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------------------


def test_every_configured_message_appears_in_both_formats() -> None:
    """A message added as configuration must not be able to hide from the report."""
    reported = {(row.format, row.message_type) for row in COVERAGE.messages}

    expected = {(MessageFormat.MT, item.value) for item in MessageType} | {
        (MessageFormat.MX, spec.message_type) for spec in mx_registry.all_specs()
    }
    assert reported == expected


@pytest.mark.parametrize(
    "message_type", [item.message_type.value for item in specification_registry.list()]
)
def test_every_mt_message_round_trips(message_type: str) -> None:
    row = next(
        item
        for item in COVERAGE.messages
        if item.format is MessageFormat.MT and item.message_type == message_type
    )

    assert row.round_trip is RoundTrip.IDENTICAL


@pytest.mark.parametrize("message_type", [s.message_type for s in mx_registry.all_specs()])
def test_every_mx_message_round_trips(message_type: str) -> None:
    row = next(
        item
        for item in COVERAGE.messages
        if item.format is MessageFormat.MX and item.message_type == message_type
    )

    assert row.round_trip is RoundTrip.IDENTICAL


def test_the_excel_reference_sheet_covers_every_configured_row() -> None:
    """Measured by reading the sheet, not by trusting it. The sheet was once hardcoded to
    three MX messages while the registry held seven, and a declared figure said 100%."""
    for row in COVERAGE.messages:
        assert row.excel.covered == row.configured, f"{row.message_type} Excel coverage"


def test_intelligence_can_find_every_configured_field() -> None:
    for row in COVERAGE.messages:
        assert row.intelligence.covered == row.configured, f"{row.message_type} search"


def test_the_builder_renders_every_configured_field() -> None:
    for row in COVERAGE.messages:
        assert row.form.covered == row.configured, f"{row.message_type} form"


def test_no_message_claims_authoritative_completeness() -> None:
    """The honest-reporting invariant, asserted where it is easiest to erode."""
    assert COVERAGE.authoritative_completeness_known is False
    for row in COVERAGE.messages:
        assert row.authoritative_completeness_known is False
        assert row.capability == "PARTIAL"
        assert row.basis is not CoverageBasis.EXTERNALLY_VERIFIED


def test_the_report_states_its_denominator_is_the_configured_subset() -> None:
    markdown = render_markdown(COVERAGE)

    assert "not a claim of ISO 15022 or ISO 20022 completeness" in markdown
    assert "Authoritative completeness denominator available: **No**" in markdown
    assert "Production-capable messages: **0**" in markdown


def test_the_report_names_the_message_definitions_that_are_unverified() -> None:
    markdown = render_markdown(COVERAGE)

    unverified = [row.message_type for row in COVERAGE.messages if row.notes]
    assert unverified, "the lifecycle messages carry an UNVERIFIED limitation"
    for message_type in unverified:
        assert message_type in markdown


def test_the_report_is_deterministic() -> None:
    """It is checked into the repository and gated by `make check`, so a timestamp or a
    set iteration order would fail the build on an unrelated commit."""
    assert render_markdown() == render_markdown()


def test_the_generated_document_is_current() -> None:
    from app.studio.coverage import DOCUMENT

    assert DOCUMENT.read_text(encoding="utf-8") == render_markdown()


def test_coverage_is_reachable_over_the_api(client: TestClient) -> None:
    body = client.get("/api/v1/coverage").json()

    assert len(body["messages"]) == len(COVERAGE.messages)
    assert body["authoritativeCompletenessKnown"] is False
    assert {row["format"] for row in body["messages"]} == {"MT", "MX"}


# --------------------------------------------------------------------------------------
# Authoritative-source readiness
# --------------------------------------------------------------------------------------


READINESS = build_readiness()


def test_every_source_class_names_a_location_and_a_setting() -> None:
    """A drop point nobody can find is not a drop point."""
    assert READINESS.sources
    for source in READINESS.sources:
        assert source.location
        assert source.setting.isupper()
        assert source.describes
        assert source.unlocks


def test_nothing_claims_to_be_authoritative_today() -> None:
    assert READINESS.fully_sourced is False
    for source in READINESS.sources:
        assert source.state is not SourceState.AUTHORITATIVE


def test_the_unverified_message_definitions_are_named_rather_than_glossed() -> None:
    definitions = next(
        item for item in READINESS.sources if item.id == "ISO20022_MESSAGE_DEFINITIONS"
    )

    assert "sese.030" in definitions.present


def test_every_drop_location_exists_so_a_file_can_actually_be_put_there() -> None:
    from pathlib import Path

    for source in READINESS.sources:
        path = Path(source.location)
        assert path.exists(), f"{source.id} points at {path}, which does not exist"


def test_readiness_is_reachable_over_the_api(client: TestClient) -> None:
    body = client.get("/api/v1/sources").json()

    assert body["fullySourced"] is False
    assert [item["id"] for item in body["sources"]] == [
        item.id for item in READINESS.sources
    ]
