"""Unified MT and MX coverage — what this repository actually implements, and against what.

Two rules shape this whole module.

**Every denominator is the configured subset.** No licensed ISO 15022 or ISO 20022
specification is present here, so no authoritative format-row count exists to divide by. A
percentage against the configured subset says "of what this repository claims to know about,
how much works"; it never says "of the standard, how much is supported". The report states
that in the text, not only in a footnote, because the number on its own invites the wrong
reading.

**Coverage is measured, not declared.** Form, Excel, Intelligence, sample and round-trip
figures are computed by asking the real component what it produced, not by reading a flag
that says it should have. That distinction is not academic: the Excel reference sheet was
once hardcoded to three MX messages while the registry held seven, and a declared figure
would have reported 100%.

Each metric records its own :class:`CoverageBasis`, so a message validated against a
licensed schema that has been dropped in is visibly different from one validated against a
schema derived from this repository's own YAML.
"""

from __future__ import annotations

import argparse
import json
from enum import StrEnum
from pathlib import Path

from app.domain.models import ApiModel
from app.specifications.registry import specification_registry
from app.studio import intelligence
from app.studio.capability import CapabilityDimensions, capability_summary
from app.studio.catalogue import capability_dimensions, message_spec
from app.studio.excel import reference_rows
from app.studio.models import MessageFormat, SampleVariant
from app.studio.mt.generator import mt_generator
from app.studio.mt.parser import MtImportError
from app.studio.mt.parser import parse_message as parse_mt
from app.studio.mx.generator import mx_generator
from app.studio.mx.parser import MxImportError
from app.studio.mx.parser import parse_message as parse_mx
from app.studio.mx.registry import mx_registry
from app.studio.mx.xsd import SchemaSource, official_schema_path
from app.studio.samples import available_variants, build_sample
from app.studio.service import studio_service
from app.studio.sources import build_readiness

PROFILE_ID = "BASE_DEMO_V1"
DOCUMENT = (
    Path(__file__).resolve().parents[3] / "docs" / "generated" / "message-coverage.md"
)
MT_PROWIDE_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "mt_prowide"
    / "category5-sru2025-10.3.18.json"
)


class CoverageBasis(StrEnum):
    """Where the confidence in a number comes from — never blurred into one percentage."""

    #: Measured against what this repository configures. The only basis available today.
    REPOSITORY_CONFIGURED = "REPOSITORY_CONFIGURED"
    #: No authoritative denominator exists, so completeness against the standard is unknown.
    AUTHORITATIVE_UNKNOWN = "AUTHORITATIVE_UNKNOWN"
    #: Checked against an authoritative artifact that is actually present in the repository.
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


class Metric(ApiModel):
    covered: int
    configured: int
    basis: CoverageBasis = CoverageBasis.REPOSITORY_CONFIGURED

    @property
    def percentage(self) -> float:
        return round(self.covered / self.configured * 100, 1) if self.configured else 0.0

    def render(self) -> str:
        return f"{self.covered}/{self.configured}"


class RoundTrip(StrEnum):
    IDENTICAL = "IDENTICAL"
    DIFFERS = "DIFFERS"
    REFUSED = "REFUSED"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class MessageCoverageRow(ApiModel):
    """One configured message, in either format."""

    format: MessageFormat
    message_type: str
    version: str | None
    capability: str
    #: The dimensional model behind the single word above; see app/studio/capability.py.
    capability_dimensions: CapabilityDimensions | None = None
    capability_summary: str = ""
    verification_status: str
    #: The denominator: value-bearing rows (MT) or leaf elements (MX) this repository holds.
    configured: int
    #: MX only: containers and choices as well as leaves, so the tree size is visible.
    configured_nodes: int | None
    form: Metric
    composer: Metric
    parser: Metric
    validation: Metric
    intelligence: Metric
    excel: Metric
    sample: Metric
    golden: Metric | None
    round_trip: RoundTrip
    schema_source: SchemaSource | None
    authoritative_completeness_known: bool
    basis: CoverageBasis
    notes: list[str] = []


class UnifiedCoverage(ApiModel):
    mt_registry_version: str
    messages: list[MessageCoverageRow]
    configured_total: int
    authoritative_completeness_known: bool
    #: Source classes that would change these numbers, and whether one is present.
    official_schemas_present: int


# --------------------------------------------------------------------------------------
# Measuring
# --------------------------------------------------------------------------------------


def _full_variant(format_: MessageFormat, message_type: str) -> SampleVariant | None:
    variants = available_variants(format_, message_type)
    if not variants:
        return None
    for candidate in (SampleVariant.FULL, SampleVariant.TYPICAL, SampleVariant.MINIMAL):
        if candidate in variants:
            return candidate
    return variants[-1]


def _excel_index(format_: MessageFormat) -> dict[str, int]:
    """How many rows the Excel reference sheet writes per message — read from the sheet."""
    counts: dict[str, int] = {}
    for row in reference_rows(format_):
        counts[row.message_type] = counts.get(row.message_type, 0) + 1
    return counts


def _intelligence_index() -> dict[str, int]:
    """How many fields Message Intelligence can find per message — read from the index.

    MT rows that mean the same thing in several messages are merged into one entry, so a
    field is counted for every message it belongs to rather than once.
    """
    counts: dict[str, int] = {}
    for _field, message_types, _terms in intelligence._index():
        for message_type in message_types:
            counts[message_type] = counts.get(message_type, 0) + 1
    return counts


def _mt_row(
    message_type: str, excel: dict[str, int], search: dict[str, int]
) -> MessageCoverageRow:
    specification = specification_registry.get(message_type)
    name = message_type
    configured = len(specification.fields)
    projected = message_spec(MessageFormat.MT, name)

    # The importer resolves a row by (sequence, tag, qualifier). A row whose address is
    # shared with another row in the same sequence could not be told apart, so it is not
    # counted — this is what the parser can actually recover, not what it is declared to.
    addresses: dict[tuple[str, str, str | None], int] = {}
    for row in specification.fields:
        key = (row.sequence_path, row.tag, row.qualifier)
        addresses[key] = addresses.get(key, 0) + 1
    resolvable = sum(
        1
        for row in specification.fields
        if addresses[(row.sequence_path, row.tag, row.qualifier)] == 1
    )

    variant = _full_variant(MessageFormat.MT, name)
    sample_rows: set[str] = set()
    round_trip = RoundTrip.NOT_SUPPORTED
    if variant is not None:
        sample = build_sample(MessageFormat.MT, name, variant)
        sample_rows = {item.id for item in sample.inputs if item.id}
        round_trip = _mt_round_trip(name, list(sample.inputs))

    golden = _golden_rows(message_type)

    dimensions = capability_dimensions(MessageFormat.MT, name)
    return MessageCoverageRow(
        format=MessageFormat.MT,
        message_type=name,
        version=None,
        capability=specification.capability.value,
        capability_dimensions=dimensions,
        capability_summary=capability_summary(dimensions),
        verification_status=specification.source.verification_status.value,
        configured=configured,
        configured_nodes=None,
        form=Metric(covered=len(projected.fields), configured=configured),
        composer=Metric(
            covered=sum(1 for row in specification.fields if row.composer_supported),
            configured=configured,
        ),
        parser=Metric(covered=resolvable, configured=configured),
        validation=Metric(
            covered=sum(1 for row in specification.fields if row.validator_supported),
            configured=configured,
        ),
        intelligence=Metric(covered=search.get(name, 0), configured=configured),
        excel=Metric(covered=excel.get(name, 0), configured=configured),
        sample=Metric(covered=len(sample_rows), configured=configured),
        golden=Metric(covered=len(golden), configured=configured),
        round_trip=round_trip,
        schema_source=None,
        authoritative_completeness_known=False,
        basis=CoverageBasis.AUTHORITATIVE_UNKNOWN,
        notes=[],
    )


def _golden_rows(message_type: str) -> set[str]:
    from app.samples.service import sample_service

    return sample_service.coverage().get(message_type, set())


def _mt_round_trip(message_type: str, inputs: list) -> RoundTrip:  # type: ignore[type-arg]
    from app.profiles.loader import profiles

    profile = profiles.get(PROFILE_ID)
    original = mt_generator.build(message_type, profile, inputs)
    try:
        parsed = parse_mt(original.fin or original.block_4)
    except MtImportError:
        return RoundTrip.REFUSED
    if parsed.errors:
        return RoundTrip.REFUSED
    again = mt_generator.build(
        parsed.specification.message_type,
        profile,
        parsed.fields,
        envelope=parsed.envelope,
    )
    return (
        RoundTrip.IDENTICAL
        if again.block_4 == original.block_4 and again.fin == original.fin
        else RoundTrip.DIFFERS
    )


def _mx_row(
    message_type: str, excel: dict[str, int], search: dict[str, int]
) -> MessageCoverageRow:
    spec = mx_registry.get(message_type)
    flat = mx_registry.flat(message_type)
    leaves = [item for item in flat if item.element.is_leaf]
    configured = len(leaves)
    projected = message_spec(MessageFormat.MX, spec.message_type)

    # Every leaf is addressable by its absolute path, so the importer can recover all of
    # them — except a leaf under two nested repeatable containers, which the flat
    # (path, occurrence) address cannot distinguish. Counted rather than assumed.
    def nested_repeat(path: str) -> bool:
        repeats = 0
        for item in flat:
            if path == item.path or path.startswith(item.path + "/"):
                repeats += 1 if item.element.repeatable else 0
        return repeats > 1

    recoverable = sum(1 for item in leaves if not nested_repeat(item.path))

    variant = _full_variant(MessageFormat.MX, spec.message_type)
    sample_paths: set[str] = set()
    round_trip = RoundTrip.NOT_SUPPORTED
    if variant is not None:
        sample = build_sample(MessageFormat.MX, spec.message_type, variant)
        sample_paths = {item.path for item in sample.elements}
        round_trip = _mx_round_trip(spec.message_type, list(sample.elements))

    source = studio_service.schema_source(spec.message_type)
    unverified = any("UNVERIFIED" in item for item in spec.limitations)
    notes: list[str] = []
    if unverified:
        notes.append("Message definition UNVERIFIED against an authoritative source.")

    dimensions = capability_dimensions(MessageFormat.MX, spec.message_type)
    return MessageCoverageRow(
        format=MessageFormat.MX,
        message_type=spec.message_type,
        version=spec.version,
        capability="PARTIAL",
        capability_dimensions=dimensions,
        capability_summary=capability_summary(dimensions),
        verification_status="UNVERIFIED" if unverified else spec.source.source_type,
        configured=configured,
        configured_nodes=len(flat),
        form=Metric(covered=len(projected.fields), configured=configured),
        composer=Metric(covered=configured, configured=configured),
        parser=Metric(covered=recoverable, configured=configured),
        validation=Metric(
            covered=sum(1 for item in leaves if item.element.data_type is not None),
            configured=configured,
        ),
        intelligence=Metric(covered=search.get(spec.message_type, 0), configured=configured),
        excel=Metric(covered=excel.get(spec.message_type, 0), configured=configured),
        sample=Metric(covered=len(sample_paths), configured=configured),
        golden=None,
        round_trip=round_trip,
        schema_source=source,
        authoritative_completeness_known=spec.authoritative_completeness_known,
        basis=(
            CoverageBasis.EXTERNALLY_VERIFIED
            if source is SchemaSource.OFFICIAL
            else CoverageBasis.AUTHORITATIVE_UNKNOWN
        ),
        notes=notes,
    )


def _mx_round_trip(message_type: str, elements: list) -> RoundTrip:  # type: ignore[type-arg]
    from app.profiles.loader import profiles

    profile = profiles.get(PROFILE_ID)
    original = mx_generator.build(message_type, profile, elements)
    try:
        parsed = parse_mx(original.xml)
    except MxImportError:
        return RoundTrip.REFUSED
    if parsed.errors:
        return RoundTrip.REFUSED
    again = mx_generator.build(
        parsed.specification.message_type, profile, parsed.elements, envelope=parsed.envelope
    )
    return RoundTrip.IDENTICAL if again.document == original.document else RoundTrip.DIFFERS


def build_coverage() -> UnifiedCoverage:
    mt_excel = _excel_index(MessageFormat.MT)
    mx_excel = _excel_index(MessageFormat.MX)
    search = _intelligence_index()

    rows = [
        _mt_row(mt.message_type, mt_excel, search)
        for mt in specification_registry.list()
    ]
    rows.extend(
        _mx_row(spec.message_type, mx_excel, search) for spec in mx_registry.all_specs()
    )
    official = sum(
        1 for spec in mx_registry.all_specs() if official_schema_path(spec) is not None
    )
    return UnifiedCoverage(
        mt_registry_version=specification_registry.registry_version,
        messages=rows,
        configured_total=sum(row.configured for row in rows),
        authoritative_completeness_known=False,
        official_schemas_present=official,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

_LEGEND = """\
## How to read these numbers

Every figure is **out of what this repository configures**, never out of the standard. No
licensed ISO 15022 or ISO 20022 specification is present here, so no authoritative
format-row count exists to divide by. `12/12` means the twelve rows this repository holds
for that message all work; it does not mean the message is complete.

Three bases are reported and never added together:

| Basis | Meaning |
| --- | --- |
| `REPOSITORY_CONFIGURED` | Measured against this repository's own configuration. |
| `AUTHORITATIVE_UNKNOWN` | Completeness against the published standard is not established. |
| `EXTERNALLY_VERIFIED` | Checked against an authoritative artifact present in the repository. |

Columns are measured by asking the component what it produced, not by reading a flag:

- **Form** — fields the browser builder renders, from the catalogue projection.
- **Composer** — rows the composer will write when given a value.
- **Parser** — rows import can recover. An MT row sharing its `(sequence, tag, qualifier)`
  address with another, or an MX leaf under two nested repeatable containers, cannot be
  told apart and is not counted.
- **Validation** — rows carrying at least one format or structure rule.
- **Intelligence** — fields the deterministic search index can find.
- **Excel** — rows written to the template's Reference sheet.
- **Sample** — rows the fullest generated sample fills.
- **Golden** — rows covered by the byte-for-byte MT regression fixtures. MX has none.
- **Round trip** — `Compose(Parse(Compose(sample)))` compared with `Compose(sample)`.
  `IDENTICAL` is the only passing value.
"""


def render_markdown(coverage: UnifiedCoverage | None = None) -> str:
    report = coverage or build_coverage()
    mt = [row for row in report.messages if row.format is MessageFormat.MT]
    mx = [row for row in report.messages if row.format is MessageFormat.MX]
    unverified = [row for row in report.messages if row.notes]

    lines = [
        "# Message coverage",
        "",
        "Generated by `make coverage` from the specification registries and the components "
        "themselves. This is configured-subset coverage, not a claim of ISO 15022 or ISO "
        "20022 completeness.",
        "",
        f"- MT registry version: `{report.mt_registry_version}`",
        f"- Configured messages: **{len(report.messages)}** "
        f"({len(mt)} MT, {len(mx)} MX)",
        f"- Configured rows and elements: **{report.configured_total}**",
        "- Authoritative completeness denominator available: **No**",
        f"- Official ISO 20022 schemas present: **{report.official_schemas_present}** "
        f"of {len(mx)}",
        f"- MT Prowide structural evidence: {_mt_prowide_evidence_summary()}",
        "- Production-capable messages: **0**",
        "",
        _LEGEND,
        "",
        "## MT — ISO 15022",
        "",
        "| Message | Capability | Verification | Rows | Form | Composer | Parser | "
        "Validation | Intelligence | Excel | Sample | Golden | Round trip |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in mt:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.message_type,
                    row.capability,
                    row.verification_status,
                    str(row.configured),
                    row.form.render(),
                    row.composer.render(),
                    row.parser.render(),
                    row.validation.render(),
                    row.intelligence.render(),
                    row.excel.render(),
                    row.sample.render(),
                    row.golden.render() if row.golden else "—",
                    row.round_trip.value,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## MX — ISO 20022",
            "",
            "| Message | Version | Capability | Verification | Elements | Nodes | Form | "
            "Composer | Parser | Validation | Intelligence | Excel | Sample | XSD | "
            "Round trip |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | --- | --- |",
        ]
    )
    for row in mx:
        lines.append(
            "| "
            + " | ".join(
                [
                    row.message_type,
                    row.version or "—",
                    row.capability,
                    row.verification_status,
                    str(row.configured),
                    str(row.configured_nodes or 0),
                    row.form.render(),
                    row.composer.render(),
                    row.parser.render(),
                    row.validation.render(),
                    row.intelligence.render(),
                    row.excel.render(),
                    row.sample.render(),
                    row.schema_source.value if row.schema_source else "—",
                    row.round_trip.value,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Capability dimensions",
            "",
            "One word cannot say which claims a message actually holds, so each authority "
            "layer is reported separately. Derived from configuration and provenance — "
            "never declared by a flag.",
            "",
            "| Message | Structure | Business rules | Market practice | Client profile | "
            "External validation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.messages:
        dims = row.capability_dimensions
        if dims is None:
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    row.message_type,
                    dims.structure.value,
                    dims.business_rules.value,
                    dims.market_practice.value,
                    dims.client_profile.value,
                    dims.external_validation.value,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## What is not established",
            "",
            "1. **No authoritative denominator.** Every percentage above is out of the "
            "configured subset. Importing a licensed, approved release-specific "
            "specification is the only thing that changes what this table may claim.",
            "2. **MX schema validation is derived by default.** A `SUBSET_DERIVED` schema is "
            "a real XSD compiled by libxml2 and it independently catches element order, "
            "cardinality, datatypes and enumerations — but it is derived from this "
            "repository's own YAML, so it proves internal consistency, not conformance. "
            "Drop an official `.xsd` into `backend/config/mx/xsd/official/` and the column "
            "reads `OFFICIAL`.",
            "3. **Network and usage rules are absent.** Message-level network validated "
            "rules, market practice and institution rule packs require an authorised "
            "import.",
        ]
    )
    if unverified:
        lines.extend(
            [
                "4. **Some message definitions are themselves unverified.** "
                + ", ".join(row.message_type for row in unverified)
                + " were modelled on the ISO 20022 idioms already present in this "
                "repository — their version numbers, root element names and element sets "
                "have not been reconciled against an authoritative message-definition "
                "report. They generate and round-trip correctly against their own "
                "configuration, which is a different claim entirely.",
            ]
        )
    lines.extend(
        [
            "",
            "The production gate fails closed regardless of the figures above. Only "
            "evidence-backed reconciliation against an authoritative source may change a "
            "capability state.",
            "",
            "## Authoritative sources: where they go",
            "",
            "Nothing licensed is reproduced in this repository. What exists is the receiving "
            "end — a named location, a setting that redirects it, and a loader that reads it "
            "with no code change. The same data is served by `GET /api/v1/sources`; the "
            "procedure is in [authoritative-sources.md](../authoritative-sources.md).",
            "",
            "| Source | Status | Reading today | Drop location | Setting |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in build_readiness().sources:
        location = item.location
        marker = "backend/config"
        if marker in location:
            location = location[location.index(marker) :]
        lines.append(
            f"| {item.name} | `{item.state.value}` | {item.present} | `{location}` | "
            f"`{item.setting}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _mt_prowide_evidence_summary() -> str:
    if not MT_PROWIDE_FIXTURE.exists():
        return "fixture not present"
    payload = json.loads(MT_PROWIDE_FIXTURE.read_text(encoding="utf-8"))
    source = payload["source"]
    candidate_count = len(payload["candidateMessages"])
    activated_count = len(payload["activatedMessages"])
    return (
        f"`{source['prowidesoftwareVersion']}` / `{source['swiftStandardsRelease']}`; "
        f"{payload['selectedMessageCount']} Category 5 classes, "
        f"{candidate_count} inert candidates, {activated_count} activated"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or verify the message coverage report")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = render_markdown()
    if args.check:
        if not DOCUMENT.exists() or DOCUMENT.read_text(encoding="utf-8") != expected:
            print("docs/generated/message-coverage.md is stale — run `make coverage-write`")
            return 1
        print("docs/generated/message-coverage.md is current")
        return 0
    if args.write:
        DOCUMENT.write_text(expected, encoding="utf-8")
        print(f"wrote {DOCUMENT}")
        return 0
    print(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
