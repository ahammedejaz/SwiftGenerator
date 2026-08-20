from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import MtMessageEvidence, MtProwideExtraction
from app.spec_engine.mt_prowide.source import DEFAULT_FIXTURE, REPO_ROOT

STRUCTURE_DIFF_DOCUMENT = REPO_ROOT / "docs" / "generated" / "mt-prowide-structure-diff.md"
COMPATIBILITY_DOCUMENT = REPO_ROOT / "docs" / "generated" / "mt-importer-compatibility.md"


@dataclass(frozen=True)
class ControlComparison:
    message_type: str
    configured_sequences: int
    prowide_sequences: int
    configured_rows: int
    rows_observed_by_tag_and_sequence: int
    missing_sequences: tuple[str, ...]
    missing_rows: tuple[str, ...]
    extra_prowide_sequences: int
    extra_prowide_field_groups: int

    @property
    def passed(self) -> bool:
        return not self.missing_sequences and not self.missing_rows


@dataclass(frozen=True)
class CompatibilitySummary:
    extracted_messages: int
    configured_messages: int
    configured_messages_observed: int
    candidate_messages: int
    activated_messages: int
    sequences: int
    fieldsets: int
    field_groups: int
    distinct_global_fields: int
    global_field_definition_errors: int


def build_compatibility_summary(
    extraction: MtProwideExtraction,
) -> CompatibilitySummary:
    configured = _configured_mt_types()
    extracted = {message.message_type for message in extraction.messages}
    return CompatibilitySummary(
        extracted_messages=len(extraction.messages),
        configured_messages=len(configured),
        configured_messages_observed=len(configured & extracted),
        candidate_messages=len(extraction.candidate_messages),
        activated_messages=len(extraction.activated_messages),
        sequences=sum(message.sequence_count for message in extraction.messages),
        fieldsets=sum(message.fieldset_count for message in extraction.messages),
        field_groups=sum(message.field_group_count for message in extraction.messages),
        distinct_global_fields=len(extraction.global_fields),
        global_field_definition_errors=sum(1 for field in extraction.global_fields if field.error),
    )


def compare_controls(extraction: MtProwideExtraction) -> list[ControlComparison]:
    from app.specifications.registry import specification_registry

    by_type = {message.message_type: message for message in extraction.messages}
    comparisons: list[ControlComparison] = []
    for spec in specification_registry.list():
        message = by_type.get(spec.message_type)
        if message is None:
            comparisons.append(
                ControlComparison(
                    message_type=spec.message_type,
                    configured_sequences=len(spec.sequences),
                    prowide_sequences=0,
                    configured_rows=len(spec.fields),
                    rows_observed_by_tag_and_sequence=0,
                    missing_sequences=tuple(sequence.code for sequence in spec.sequences),
                    missing_rows=tuple(row.row_id for row in spec.fields),
                    extra_prowide_sequences=0,
                    extra_prowide_field_groups=0,
                )
            )
            continue
        sequence_codes = {sequence.path: sequence.code for sequence in message.sequences}
        prowide_sequence_codes = set(sequence_codes.values())
        configured_sequence_codes = {sequence.code for sequence in spec.sequences}
        prowide_pairs = {
            (sequence_codes.get(group.sequence_path, "UNKNOWN"), tag)
            for group in message.field_groups
            for tag in group.tags
        }
        configured_pairs = {(row.sequence_code, row.tag) for row in spec.fields}
        missing_rows = [
            row.row_id
            for row in spec.fields
            if (row.sequence_code, row.tag) not in prowide_pairs
        ]
        comparisons.append(
            ControlComparison(
                message_type=spec.message_type,
                configured_sequences=len(spec.sequences),
                prowide_sequences=len(message.sequences),
                configured_rows=len(spec.fields),
                rows_observed_by_tag_and_sequence=sum(
                    1 for row in spec.fields if (row.sequence_code, row.tag) in prowide_pairs
                ),
                missing_sequences=tuple(sorted(configured_sequence_codes - prowide_sequence_codes)),
                missing_rows=tuple(missing_rows),
                extra_prowide_sequences=len(prowide_sequence_codes - configured_sequence_codes),
                extra_prowide_field_groups=sum(
                    1
                    for group in message.field_groups
                    if all(
                        (sequence_codes.get(group.sequence_path, "UNKNOWN"), tag)
                        not in configured_pairs
                        for tag in group.tags
                    )
                ),
            )
        )
    return comparisons


def render_compatibility(
    extraction: MtProwideExtraction | None = None,
) -> str:
    report = extraction or load_extraction()
    summary = build_compatibility_summary(report)
    lines = [
        "# MT Prowide Importer Compatibility",
        "",
        "Generated by `make mt-prowide-check` from the committed Prowide-derived "
        "Category 5 evidence fixture. This is a build-time compatibility report, not a "
        "Swift conformance statement.",
        "",
        "## Source",
        "",
        f"- Source: `{report.source.source_name}`",
        f"- Artifact: `{report.source.artifact_coordinate}`",
        f"- Prowide version: `{report.source.prowidesoftware_version}`",
        f"- Swift release represented by artifact: `{report.source.swift_standards_release}`",
        f"- Verified date: `{report.source.verified_at}`",
        f"- License declared by Maven Central/POM: `{report.source.verification.license}`",
        "",
        "## Counts",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| Prowide Category 5 message classes extracted | {summary.extracted_messages} |",
        (
            "| Configured MT messages observed in Prowide | "
            f"{summary.configured_messages_observed}/{summary.configured_messages} |"
        ),
        f"| Candidate-only Category 5 messages | {summary.candidate_messages} |",
        f"| Newly activated messages | {summary.activated_messages} |",
        f"| Prowide-observed sequences | {summary.sequences} |",
        f"| Prowide-observed fieldsets | {summary.fieldsets} |",
        f"| Prowide-observed field groups | {summary.field_groups} |",
        f"| Reflected global field classes | {summary.distinct_global_fields} |",
        f"| Global field reflection errors | {summary.global_field_definition_errors} |",
        "",
        "## Runtime Boundary",
        "",
        "| Boundary | Status |",
        "| --- | --- |",
        "| Java/Prowide in normal FastAPI generation path | `NO` |",
        "| Maven or Gradle required at runtime | `NO` |",
        "| Build-time jar cache committed | `NO` |",
        "| Candidate messages exposed in catalogue | `NO` |",
        "| Existing MT structures overwritten | `NO` |",
        "",
        "## Evidence Boundaries",
        "",
        "| Claim | Status |",
        "| --- | --- |",
        "| Message class exists in Prowide | `OBSERVED` |",
        "| Sequence delimiter code from `START_END_16RS` | `OBSERVED` |",
        (
            "| Field group presence from generated Prowide source scheme | "
            "`PROWIDE_DERIVED_STRUCTURAL_EVIDENCE` |"
        ),
        "| Global field parser/validator patterns | `OBSERVED_FROM_FIELD_CLASS` |",
        "| Qualifier legality in a specific message | `UNKNOWN` |",
        "| Code-list legality in a specific message | `UNKNOWN` |",
        "| Network validation and usage rules | `UNKNOWN` |",
        "| Swift certification or conformance | `NOT_CLAIMED` |",
        "",
        "## Candidate Lifecycle",
        "",
        "All non-configured Category 5 message classes remain candidates. A candidate can be "
        "reviewed in a later phase, but this importer does not promote it into "
        "`backend/config/specifications/` and does not create MT knowledge records. The "
        "configured runtime set therefore remains unchanged.",
        "",
        "Candidate message types:",
        "",
        _wrap_codes(report.candidate_messages),
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append("")
    return "\n".join(lines)


def render_structure_diff(
    extraction: MtProwideExtraction | None = None,
) -> str:
    report = extraction or load_extraction()
    comparisons = compare_controls(report)
    lines = [
        "# MT Prowide Structure Diff",
        "",
        "Generated by `make mt-prowide-check`. The comparison checks the installed MT "
        "configured subset against Prowide-derived Category 5 structure evidence by "
        "sequence delimiter code and tag option only. It deliberately does not infer "
        "qualifier legality, full message completeness, business rules, or Swift "
        "conformance.",
        "",
        "## Configured Control Set",
        "",
        (
            "| Message | Configured sequences | Prowide sequences | Configured rows | "
            "Rows observed by tag+sequence | Missing sequences | Missing rows | "
            "Extra Prowide sequences | Extra Prowide field groups |"
        ),
        "| --- | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |",
    ]
    for item in comparisons:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.message_type,
                    str(item.configured_sequences),
                    str(item.prowide_sequences),
                    str(item.configured_rows),
                    str(item.rows_observed_by_tag_and_sequence),
                    ", ".join(item.missing_sequences) or "-",
                    _summarise_missing(item.missing_rows),
                    str(item.extra_prowide_sequences),
                    str(item.extra_prowide_field_groups),
                ]
            )
            + " |"
        )
    missing = [item for item in comparisons if not item.passed]
    lines.extend(
        [
            "",
            "## Result",
            "",
            f"- Configured messages checked: `{len(comparisons)}`",
            f"- Configured messages with missing Prowide tag/sequence evidence: `{len(missing)}`",
            "- New runtime messages installed: `0`",
            "- Existing installed messages overwritten: `0`",
            "",
            "The extra Prowide rows are evidence of the expected full-message surface being "
            "larger than this repository's reviewed subset. They are not activated.",
            "",
        ]
    )
    return "\n".join(lines)


def check_reports(fixture: Path = DEFAULT_FIXTURE) -> list[str]:
    extraction = load_extraction(fixture)
    expected = {
        STRUCTURE_DIFF_DOCUMENT: render_structure_diff(extraction),
        COMPATIBILITY_DOCUMENT: render_compatibility(extraction),
    }
    stale = [
        str(path)
        for path, text in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]
    return stale


def write_reports(fixture: Path = DEFAULT_FIXTURE) -> None:
    extraction = load_extraction(fixture)
    outputs = {
        STRUCTURE_DIFF_DOCUMENT: render_structure_diff(extraction),
        COMPATIBILITY_DOCUMENT: render_compatibility(extraction),
    }
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def mt_source_summary_for_coverage() -> str:
    if not DEFAULT_FIXTURE.exists():
        return "`NOT_PRESENT`"
    extraction = load_extraction(DEFAULT_FIXTURE)
    summary = build_compatibility_summary(extraction)
    return (
        f"`PROWIDE_DERIVED_STRUCTURAL_EVIDENCE` "
        f"({summary.configured_messages_observed}/{summary.configured_messages} configured MT, "
        f"{summary.candidate_messages} candidate-only, 0 activated)"
    )


def _configured_mt_types() -> set[str]:
    from app.specifications.registry import specification_registry

    return {message.message_type for message in specification_registry.list()}


def _wrap_codes(codes: list[str]) -> str:
    if not codes:
        return "`none`"
    chunks: list[str] = []
    current: list[str] = []
    for code in codes:
        current.append(f"`{code}`")
        if len(current) == 12:
            chunks.append(", ".join(current))
            current = []
    if current:
        chunks.append(", ".join(current))
    return "\n".join(chunks)


def _summarise_missing(rows: tuple[str, ...]) -> str:
    if not rows:
        return "-"
    if len(rows) <= 4:
        return ", ".join(rows)
    return ", ".join(rows[:4]) + f" (+{len(rows) - 4})"


def message_by_type(extraction: MtProwideExtraction) -> dict[str, MtMessageEvidence]:
    return {message.message_type: message for message in extraction.messages}
