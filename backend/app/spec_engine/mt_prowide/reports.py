from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import (
    AuthoringReadinessStatus,
    MtMessageEvidence,
    MtProwideExtraction,
)
from app.spec_engine.mt_prowide.source import DEFAULT_FIXTURE, REPO_ROOT
from app.specifications.models import FieldSpecification

STRUCTURE_DIFF_DOCUMENT = REPO_ROOT / "docs" / "generated" / "mt-prowide-structure-diff.md"
COMPATIBILITY_DOCUMENT = REPO_ROOT / "docs" / "generated" / "mt-importer-compatibility.md"
MULTICATEGORY_COVERAGE_DOCUMENT = (
    REPO_ROOT / "docs" / "generated" / "mt-multicategory-coverage.md"
)

REPRESENTATIVE_TYPES = [
    "MT103",
    "MT103_STP",
    "MT103_REMIT",
    "MT202",
    "MT202COV",
    "MT300",
    "MT320",
    "MT400",
    "MT700",
    "MT707",
    "MT760",
    "MT900",
    "MT910",
    "MT940",
    "MT942",
    "MT950",
]


@dataclass(frozen=True)
class DifferenceFinding:
    row_id: str
    classification: str


@dataclass(frozen=True)
class ControlComparison:
    message_type: str
    configured_sequences: int
    prowide_sequences: int
    configured_rows: int
    rows_observed_by_tag_and_sequence: int
    missing_sequences: tuple[str, ...]
    missing_rows: tuple[str, ...]
    missing_row_findings: tuple[DifferenceFinding, ...]
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
    variants: int


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
        variants=sum(1 for message in extraction.messages if message.variant),
    )


def compare_controls(extraction: MtProwideExtraction) -> list[ControlComparison]:
    from app.specifications.registry import specification_registry

    by_type = message_by_type(extraction)
    comparisons: list[ControlComparison] = []
    for spec in specification_registry.list():
        message = by_type.get(spec.message_type)
        if message is None:
            findings = tuple(
                DifferenceFinding(row.row_id, "SOURCE_MODEL_DIFFERENCE")
                for row in spec.fields
            )
            comparisons.append(
                ControlComparison(
                    message_type=spec.message_type,
                    configured_sequences=len(spec.sequences),
                    prowide_sequences=0,
                    configured_rows=len(spec.fields),
                    rows_observed_by_tag_and_sequence=0,
                    missing_sequences=tuple(sequence.code for sequence in spec.sequences),
                    missing_rows=tuple(row.row_id for row in spec.fields),
                    missing_row_findings=findings,
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
        findings = tuple(
            DifferenceFinding(row.row_id, _classify_missing_row(row, message, sequence_codes))
            for row in spec.fields
            if (row.sequence_code, row.tag) not in prowide_pairs
        )
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
                missing_row_findings=findings,
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
        "multi-category evidence fixture. This is a build-time compatibility report, not "
        "a Swift conformance statement.",
        "",
        "## Source",
        "",
        f"- Source: `{report.source.source_name}`",
        f"- Artifact: `{report.source.artifact_coordinate}`",
        f"- Prowide version: `{report.source.prowidesoftware_version}`",
        f"- Swift release represented by artifact: `{report.source.swift_standards_release}`",
        f"- Verified date: `{report.source.verified_at}`",
        f"- License declared by Maven Central/POM: `{report.source.verification.license}`",
        f"- Extracted scope: `{report.extracted_scope}`",
        "",
        "## Counts",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| Prowide MT source model classes extracted | {summary.extracted_messages} |",
        f"| Categories discovered | {len(report.discovered_categories)} |",
        f"| Distinct variant source models | {summary.variants} |",
        (
            "| Configured MT messages observed in Prowide | "
            f"{summary.configured_messages_observed}/{summary.configured_messages} |"
        ),
        f"| Candidate-only source models | {summary.candidate_messages} |",
        f"| Newly activated messages | {summary.activated_messages} |",
        f"| Prowide-observed sequences | {summary.sequences} |",
        f"| Prowide-observed fieldsets | {summary.fieldsets} |",
        f"| Prowide-observed field groups | {summary.field_groups} |",
        f"| Reflected global field classes | {summary.distinct_global_fields} |",
        f"| Global field reflection errors | {summary.global_field_definition_errors} |",
        "",
        "## Category Coverage",
        "",
        "| Category | Source models |",
        "| --- | ---: |",
    ]
    for category in report.discovered_categories:
        lines.append(f"| MT{category}xx | {report.category_counts[str(category)]} |")
    lines.extend(
        [
            "",
            "## Importer Capability Matrix",
            "",
            "| Capability | Status |",
            "| --- | --- |",
            "| Class discovery | `OBSERVED_FROM_SOURCE_JAR` |",
            "| Category discovery | `OBSERVED_FROM_SOURCE_JAR` |",
            "| Sequence extraction | `OBSERVED_FROM_SOURCE_SCHEME` |",
            "| Nested sequence extraction | `OBSERVED_WHERE_SOURCE_SCHEME_EXPOSES_IT` |",
            "| Repeated sequence extraction | `OBSERVED_REPEATABILITY_ONLY` |",
            "| Fieldsets | `OBSERVED_FROM_SOURCE_SCHEME` |",
            "| Message field-use | `STRUCTURAL_EVIDENCE_ONLY` |",
            "| Options | `OBSERVED_FROM_SOURCE_SCHEME` |",
            "| Qualifiers | `UNKNOWN_MESSAGE_CONTEXT` |",
            "| Global components | `OBSERVED_FROM_FIELD_CLASS` |",
            "| Field patterns | `GLOBAL_ONLY` |",
            "| Requiredness | `SOURCE_PRESENCE_ONLY_NOT_RUNTIME_AUTHORITY` |",
            "| Cardinality | `OBSERVED_REPEATABILITY_OR_UNKNOWN` |",
            "| Prowide parse | `MT541_CONTROL_ONLY` |",
            "| Our parser | `CONFIGURED_RUNTIME_MESSAGES_ONLY` |",
            "| Round trip | `CONFIGURED_RUNTIME_MESSAGES_ONLY` |",
            "| Category coverage | `MULTICATEGORY_SOURCE_DISCOVERY` |",
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
            "## Candidate Lifecycle",
            "",
            "Non-configured source models remain inert candidates. This importer does not promote "
            "them into `backend/config/specifications/`, create MT knowledge records, add "
            "samples, or expose them in Create Message.",
            "",
            "Candidate counts by category:",
            "",
            "| Category | Candidate source models |",
            "| --- | ---: |",
        ]
    )
    candidate_by_category = Counter(
        str(message.category)
        for message in report.messages
        if message.message_type in report.candidate_messages
    )
    for category in report.discovered_categories:
        lines.append(f"| MT{category}xx | {candidate_by_category[str(category)]} |")
    lines.extend(
        [
            "",
            "Representative candidates:",
            "",
            _wrap_codes(_representative_candidate_codes(report)),
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append("")
    return "\n".join(lines)


def render_structure_diff(
    extraction: MtProwideExtraction | None = None,
) -> str:
    report = extraction or load_extraction()
    comparisons = compare_controls(report)
    missing = [item for item in comparisons if not item.passed]
    classification_counts = _classification_counts(comparisons)
    lines = [
        "# MT Prowide Structure Diff",
        "",
        "Generated by `make mt-prowide-check`. The comparison checks the installed MT "
        "configured subset against Prowide-derived multi-category structure evidence by "
        "sequence delimiter code and tag option only. It deliberately does not infer "
        "qualifier legality, full message completeness, business rules, or Swift "
        "conformance.",
        "",
        "## Current Configured MTs",
        "",
        (
            "| Message | Configured sequences | Prowide sequences | Configured rows | "
            "Rows observed by tag+sequence | Missing sequences | Missing rows | "
            "Dominant classification | Extra Prowide sequences | Extra Prowide field groups |"
        ),
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: |",
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
                    _dominant_classification(item),
                    str(item.extra_prowide_sequences),
                    str(item.extra_prowide_field_groups),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Representative New MTs",
            "",
            "| Source model | Category | Sequences | Field groups | Authoring status | "
            "Parse proof |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for message in _representative_messages(report):
        lines.append(
            f"| {message.message_type} | {message.category} | {message.sequence_count} | "
            f"{message.field_group_count} | `{message.authoring_status.value}` | "
            "`NOT_RUN_NO_RUNTIME_SPEC` |"
        )
    absent = [code for code in REPRESENTATIVE_TYPES if code not in message_by_type(report)]
    if absent:
        lines.extend(["", f"Representative examples absent from source: {_wrap_codes(absent)}"])
    lines.extend(
        [
            "",
            "## Summary Metrics",
            "",
            f"- Configured messages checked: `{len(comparisons)}`",
            f"- Configured messages with missing Prowide tag/sequence evidence: `{len(missing)}`",
            f"- Difference findings classified: `{sum(classification_counts.values())}`",
            f"- New runtime messages installed: `{len(report.activated_messages)}`",
            "- Existing installed messages overwritten: `0`",
            "",
            "Classification counts:",
            "",
            "| Classification | Count |",
            "| --- | ---: |",
        ]
    )
    for classification, count in sorted(classification_counts.items()):
        lines.append(f"| `{classification}` | {count} |")
    lines.extend(
        [
            "",
            "## Unknown / Blocked",
            "",
            "- Extra Prowide rows are evidence of the expected full-message surface being larger "
            "than this repository's reviewed subset. They are not activated.",
            "- Missing rows are not repaired from Prowide alone.",
            "- Qualifier legality, code-list legality, business rules and network rules remain "
            "`UNKNOWN` without authorised message-specific source material.",
            "",
        ]
    )
    return "\n".join(lines)


def render_multicategory_coverage(
    extraction: MtProwideExtraction | None = None,
) -> str:
    report = extraction or load_extraction()
    summary = build_compatibility_summary(report)
    authoring_counts = Counter(message.authoring_status.value for message in report.messages)
    blocker_counts = Counter(
        blocker
        for message in report.messages
        if message.message_type in report.candidate_messages
        for blocker in message.authoring_blockers
    )
    lines = [
        "# MT Multicategory Coverage",
        "",
        "Generated by `make mt-prowide-check` from the committed Prowide-derived "
        "multi-category evidence fixture.",
        "",
        "## Status Model",
        "",
        "| Area | Status |",
        "| --- | --- |",
        "| PHASE_4_FOUNDATION | `COMPLETE` |",
        "| MULTICATEGORY_SOURCE_DISCOVERY | `COMPLETE` |",
        "| MULTICATEGORY_STRUCTURE_EXTRACTION | `COMPLETE` |",
        "| EXISTING_MT_RECONCILIATION | `COMPLETE` |",
        "| CROSS_CATEGORY_PARSE_PROOF | `PARTIAL` |",
        "| AUTHORING_READINESS_ANALYSIS | `COMPLETE` |",
        "| NEW_RUNTIME_MT_ACTIVATIONS | `0` |",
        "| PHASE_5_REAL_SOURCE_READY | `NO` |",
        "",
        "## Source",
        "",
        f"- Source: `{report.source.source_name}`",
        f"- Artifact: `{report.source.artifact_coordinate}`",
        f"- Prowide version: `{report.source.prowidesoftware_version}`",
        f"- Swift release represented by artifact: `{report.source.swift_standards_release}`",
        f"- License: `{report.source.verification.license}`",
        "",
        "## Source Model Counts",
        "",
        "| Measure | Count |",
        "| --- | ---: |",
        f"| Total MT source models | {summary.extracted_messages} |",
        f"| Extracted structures | {summary.extracted_messages} |",
        f"| Existing configured overlap | {summary.configured_messages_observed} |",
        f"| Candidate-only source models | {summary.candidate_messages} |",
        f"| Structure-compilable evidence records | {summary.extracted_messages} |",
        "| Cross-engine parsed source models | 1 |",
        "| Authoring-ready source models | 0 |",
        f"| Blocked candidate source models | {summary.candidate_messages} |",
        "",
        "## By Category",
        "",
        "| Category | Source models | Extracted | Candidate-only |",
        "| --- | ---: | ---: | ---: |",
    ]
    candidate_by_category = Counter(
        str(message.category)
        for message in report.messages
        if message.message_type in report.candidate_messages
    )
    for category in report.discovered_categories:
        key = str(category)
        lines.append(
            f"| MT{category}xx | {report.category_counts[key]} | "
            f"{report.category_counts[key]} | {candidate_by_category[key]} |"
        )
    lines.extend(
        [
            "",
            "## Authoring Readiness",
            "",
            "| Status | Source models |",
            "| --- | ---: |",
        ]
    )
    for status in AuthoringReadinessStatus:
        lines.append(f"| `{status.value}` | {authoring_counts[status.value]} |")
    lines.extend(
        [
            "",
            "Candidate blockers:",
            "",
            "| Blocker | Source models |",
            "| --- | ---: |",
        ]
    )
    for blocker, count in sorted(blocker_counts.items()):
        lines.append(f"| `{blocker}` | {count} |")
    lines.extend(
        [
            "",
            "## Representative Investigation",
            "",
            "| Source model | Present | Category | Structure | Parse proof | Authoring status |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
    )
    by_type = message_by_type(report)
    for code in REPRESENTATIVE_TYPES:
        message = by_type.get(code)
        if message is None:
            lines.append(f"| {code} | `NO` | - | - | `NOT_RUN_ABSENT` | - |")
            continue
        lines.append(
            f"| {code} | `YES` | {message.category} | "
            f"{message.sequence_count} seq / {message.field_group_count} groups | "
            "`NOT_RUN_NO_RUNTIME_SPEC` | "
            f"`{message.authoring_status.value}` |"
        )
    lines.extend(
        [
            "",
            "## Cross-Engine Parse",
            "",
            "| Message | Basis | Result |",
            "| --- | --- | --- |",
            "| MT541 | Repository configured sample -> StudioService -> FIN -> Prowide parser | "
            "`PASS_IN_VERIFY_TARGET` |",
            "| Representative non-Category-5 candidates | Source structures only, no runtime "
            "spec | `NOT_RUN_NO_RUNTIME_SPEC` |",
            "",
            "## Phase 5 Readiness",
            "",
            "PHASE_5_REAL_SOURCE_READY = `NO`. No authorised message-specific MT semantic source "
            "material is present in this branch. Phase 5 needs approved SWIFT/UHB material, "
            "authorised specification metadata, approved MyStandards/client exports or "
            "reviewed client rule packs.",
            "",
        ]
    )
    return "\n".join(lines)


def check_reports(fixture: Path = DEFAULT_FIXTURE) -> list[str]:
    extraction = load_extraction(fixture)
    expected = {
        STRUCTURE_DIFF_DOCUMENT: render_structure_diff(extraction),
        COMPATIBILITY_DOCUMENT: render_compatibility(extraction),
        MULTICATEGORY_COVERAGE_DOCUMENT: render_multicategory_coverage(extraction),
    }
    return [
        str(path)
        for path, text in expected.items()
        if not path.exists() or path.read_text(encoding="utf-8") != text
    ]


def write_reports(fixture: Path = DEFAULT_FIXTURE) -> None:
    extraction = load_extraction(fixture)
    outputs = {
        STRUCTURE_DIFF_DOCUMENT: render_structure_diff(extraction),
        COMPATIBILITY_DOCUMENT: render_compatibility(extraction),
        MULTICATEGORY_COVERAGE_DOCUMENT: render_multicategory_coverage(extraction),
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
        f"`{extraction.source.prowidesoftware_version}` / "
        f"`{extraction.source.swift_standards_release}`; "
        f"{summary.extracted_messages} source models across "
        f"{len(extraction.discovered_categories)} categories, "
        f"{summary.candidate_messages} inert candidates, 0 activated"
    )


def message_by_type(extraction: MtProwideExtraction) -> dict[str, MtMessageEvidence]:
    return {message.message_type: message for message in extraction.messages}


def _configured_mt_types() -> set[str]:
    from app.specifications.registry import specification_registry

    return {message.message_type for message in specification_registry.list()}


def _classify_missing_row(
    row: FieldSpecification,
    message: MtMessageEvidence,
    sequence_codes: dict[str, str],
) -> str:
    prowide_sequence_codes = set(sequence_codes.values())
    if row.sequence_code not in prowide_sequence_codes:
        return "SEQUENCE_DELIMITER_MATCHING_LIMITATION"
    same_sequence_groups = [
        group
        for group in message.field_groups
        if sequence_codes.get(group.sequence_path, "UNKNOWN") == row.sequence_code
    ]
    field_number = _field_number(row.tag)
    if any(group.field_number == field_number for group in same_sequence_groups):
        return "OPTION_MAPPING_DIFFERENCE"
    if any(row.tag in group.tags for group in message.field_groups):
        return "REPOSITORY_CONFIGURATION_DIFFERENCE"
    if same_sequence_groups:
        return "SOURCE_MODEL_DIFFERENCE"
    return "COMPARISON_LIMITATION"


def _field_number(tag: str) -> str:
    match = re.match(r"^\d{2,3}", tag)
    return match.group(0) if match else tag


def _classification_counts(comparisons: list[ControlComparison]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for comparison in comparisons:
        for finding in comparison.missing_row_findings:
            counter[finding.classification] += 1
    return counter


def _dominant_classification(comparison: ControlComparison) -> str:
    if not comparison.missing_row_findings:
        return "-"
    counts = Counter(finding.classification for finding in comparison.missing_row_findings)
    return counts.most_common(1)[0][0]


def _representative_messages(extraction: MtProwideExtraction) -> list[MtMessageEvidence]:
    by_type = message_by_type(extraction)
    selected: list[MtMessageEvidence] = []
    for code in REPRESENTATIVE_TYPES:
        message = by_type.get(code)
        if message is not None and message.message_type in extraction.candidate_messages:
            selected.append(message)
    by_category = {message.category for message in selected}
    for category in extraction.discovered_categories:
        if category in by_category:
            continue
        candidate = next(
            (
                message
                for message in extraction.messages
                if message.category == category
                and message.message_type in extraction.candidate_messages
            ),
            None,
        )
        if candidate is not None:
            selected.append(candidate)
    return selected


def _representative_candidate_codes(extraction: MtProwideExtraction) -> list[str]:
    return [message.message_type for message in _representative_messages(extraction)]


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
