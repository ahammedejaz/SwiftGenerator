"""MT semantic-source readiness and canonical reference validation.

This module is offline/developer tooling. It bridges Phase 4B Prowide-derived structural
references to the Phase 2 Rule Pack engine without making Prowide a runtime semantic
authority. A resolved canonical MT reference is evidence metadata; a runtime rule still
compiles through the installed MT row ids/triples the generic rule engine already uses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.rule_engine.diagnostics import RuleFinding, RuleFindingCode, RuleFindingLog
from app.rule_engine.models import RuleSourceType
from app.rule_engine.mt_mrg.pipeline import MrgSourceCatalogue
from app.rule_engine.refs import FieldRef, StructureIndex
from app.rule_engine.sources import (
    ADAPTER_BY_SUFFIX,
    SourceBundle,
    SourceManifest,
    rule_source_directory,
)
from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import (
    MtFieldGroupEvidence,
    MtMessageEvidence,
    MtProwideExtraction,
    MtSequenceEvidence,
)
from app.spec_engine.mt_prowide.references import MtStructuralReference
from app.specifications.registry import specification_registry
from app.studio.models import MessageFormat

SEMANTIC_READINESS_DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "generated"
    / "mt-semantic-readiness.md"
)
SOURCE_READINESS_DOCUMENT = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "generated"
    / "mt-semantic-source-readiness.md"
)

REPRESENTATIVE_CANDIDATES = (
    "MT103",
    "MT103_STP",
    "MT103_REMIT",
    "MT202",
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
)

MT_SEMANTIC_SOURCE_TYPES = frozenset(
    {
        RuleSourceType.OPERATOR_SUPPLIED_MT_GUIDE,
        RuleSourceType.OPERATOR_SUPPLIED_MYSTANDARDS_EXPORT,
        RuleSourceType.OPERATOR_SUPPLIED_INTERNAL_RULE_SOURCE,
        RuleSourceType.OPERATOR_SUPPLIED_CLIENT_GUIDELINE,
        RuleSourceType.OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL,
        RuleSourceType.OFFICIAL_ISO_15022_DOCUMENTATION,
    }
)

_TAG = re.compile(r"^(?P<number>\d{2})(?P<option>[A-Z]?)$")


@dataclass(frozen=True)
class MtSemanticReferenceRequest:
    message_type: str
    sequence_path: str
    tag: str
    standards_release: str | None = None
    option: str | None = None
    qualifier: str | None = None
    component: int | None = None
    sequence_occurrence: int | None = None


@dataclass(frozen=True)
class MtSemanticReferenceResolution:
    canonical: MtStructuralReference
    runtime_field: FieldRef | None
    runtime_field_id: str | None
    qualifier_status: str
    source_release: str

    @property
    def canonical_id(self) -> str:
        return self.canonical.canonical_id


def resolve_mt_semantic_reference(
    extraction: MtProwideExtraction,
    request: MtSemanticReferenceRequest,
    *,
    index: StructureIndex | None = None,
) -> tuple[MtSemanticReferenceResolution | None, tuple[RuleFinding, ...]]:
    """Resolve one MT semantic target against structural and installed runtime evidence."""

    log = RuleFindingLog()
    index = index or StructureIndex()
    source_release = extraction.source.swift_standards_release
    message = _message(extraction, request.message_type)
    subject = request.message_type

    if request.standards_release and request.standards_release != source_release:
        log.error(
            RuleFindingCode.MT_RULE_SRU_MISMATCH,
            f"{request.message_type} source says {request.standards_release}, but the "
            f"loaded MT structural evidence is {source_release}.",
            "Re-run against matching source and structure releases.",
            subject=subject,
        )
        return None, tuple(log.findings)

    if message is None:
        log.error(
            RuleFindingCode.MT_RULE_MESSAGE_NOT_FOUND,
            f"No Prowide MT source model named {request.message_type} is present.",
            "Use a message present in the pinned MT structural fixture.",
            subject=subject,
        )
        return None, tuple(log.findings)

    sequence = _sequence_path(message, request.sequence_path)
    if sequence is None:
        log.error(
            RuleFindingCode.MT_RULE_SEQUENCE_NOT_FOUND,
            f"{request.message_type} has no sequence {request.sequence_path}.",
            "Use a sequence path or delimiter code observed for this source model.",
            subject=subject,
            location=request.sequence_path,
        )
        return None, tuple(log.findings)

    full_tag = _full_tag(request, log)
    if full_tag is None:
        return None, tuple(log.findings)

    groups = [
        group
        for group in message.field_groups
        if group.sequence_path == sequence.path and full_tag in group.tags
    ]
    if not groups:
        log.error(
            RuleFindingCode.MT_RULE_FIELD_NOT_FOUND,
            f"{request.message_type} has no {full_tag} field group in {sequence.code}.",
            "Name a tag observed in that message sequence.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}",
        )
        return None, tuple(log.findings)
    if len(groups) > 1 and request.qualifier is None:
        log.error(
            RuleFindingCode.MT_RULE_REFERENCE_AMBIGUOUS,
            f"{request.message_type} has multiple {full_tag} groups in {sequence.code}.",
            "Add enough context for a single message-level field group.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}",
        )
        return None, tuple(log.findings)
    group = groups[0]
    resolved_option = _resolved_option(full_tag, group)
    observed_options = {_resolved_option(full_tag, item) for item in groups}
    if len(observed_options) > 1:
        log.error(
            RuleFindingCode.MT_RULE_OPTION_NOT_RESOLVED,
            f"{full_tag} has inconsistent options in {sequence.code}.",
            "Keep the tag and option aligned with one observed field group.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}",
        )
        return None, tuple(log.findings)
    if request.option and resolved_option != request.option:
        log.error(
            RuleFindingCode.MT_RULE_OPTION_NOT_RESOLVED,
            f"{full_tag} resolves to option {resolved_option or 'NONE'}, not {request.option}.",
            "Keep the tag and option aligned.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}",
        )
        return None, tuple(log.findings)

    component_ok = _component_ok(extraction, full_tag, request.component)
    if not component_ok:
        log.error(
            RuleFindingCode.MT_RULE_COMPONENT_NOT_FOUND,
            f"{full_tag} has no reflected component {request.component}.",
            "Reference only components observed on the global field class.",
            subject=subject,
            location=f"{full_tag}:C{request.component}",
        )
        return None, tuple(log.findings)

    runtime_field, runtime_id, qualifier_status = _runtime_field(
        index, request, sequence.code, full_tag
    )
    if request.qualifier and runtime_field is None and index.known(
        MessageFormat.MT, request.message_type
    ):
        log.error(
            RuleFindingCode.MT_RULE_QUALIFIER_NOT_RESOLVED,
            f"{request.message_type} has no installed runtime row for "
            f"{sequence.code}:{full_tag}:{request.qualifier}.",
            "A semantic qualifier can become runtime-active only when the installed MT "
            "structure declares that exact row.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}:{request.qualifier}",
        )
        return None, tuple(log.findings)
    if request.qualifier is None and runtime_field is None and _runtime_ambiguous(
        index, request.message_type, sequence.code, full_tag
    ):
        log.error(
            RuleFindingCode.MT_RULE_REFERENCE_AMBIGUOUS,
            f"{request.message_type} {sequence.code}:{full_tag} needs a qualifier to "
            "select one installed runtime row.",
            "Provide the exact qualifier from the authorised source.",
            subject=subject,
            location=f"{sequence.code}:{full_tag}",
        )
        return None, tuple(log.findings)

    canonical = MtStructuralReference(
        source_release=source_release,
        message_type=message.base_message_type,
        source_model=message.source_model,
        sequence_path=sequence.code,
        sequence_occurrence=request.sequence_occurrence,
        tag=full_tag,
        option=resolved_option,
        qualifier=request.qualifier,
        component=request.component,
    )
    return (
        MtSemanticReferenceResolution(
            canonical=canonical,
            runtime_field=runtime_field,
            runtime_field_id=runtime_id,
            qualifier_status=qualifier_status,
            source_release=source_release,
        ),
        tuple(log.findings),
    )


def render_semantic_readiness(
    extraction: MtProwideExtraction | None = None,
    manifest: SourceManifest | None = None,
) -> str:
    extraction = extraction or load_extraction()
    manifest = manifest or SourceManifest()
    configured = {item.message_type for item in specification_registry.list()}
    real_sources = _real_mt_sources(manifest)
    synthetic_sources = _synthetic_mt_sources(manifest)
    source_by_message = {
        message: source.source_id
        for source in [*real_sources, *synthetic_sources]
        for message in source.message_identifiers
    }
    by_type = {message.message_type: message for message in extraction.messages}
    rows = []
    for message_type in [*sorted(configured), *REPRESENTATIVE_CANDIDATES]:
        message = by_type.get(message_type)
        if message is None:
            continue
        installed = message_type in configured
        source_id = source_by_message.get(message_type)
        rows.append(
            (
                message_type,
                extraction.source.swift_standards_release,
                "Prowide structural evidence",
                "YES" if installed else "NO",
                source_id or "NO",
                "SYNTHETIC_ONLY" if source_id and not real_sources else "NO",
                "YES" if source_id else "NO",
                "YES" if installed else "NO",
                "REVIEW_REQUIRED_READY" if source_id else "NO_SOURCE",
                "NO",
                "NO",
                "NO",
                "PARTIAL" if installed else "STRUCTURAL_EVIDENCE_ONLY",
                _readiness_blocker(installed, bool(source_id)),
            )
        )
    lines = [
        "# MT Semantic Readiness",
        "",
        "Generated by `make mt-rule-check`. Structural discovery is not semantic "
        "readiness, and candidate rules are not runtime-active.",
        "",
        "## Status",
        "",
        "| Status | Value |",
        "| --- | --- |",
        "| PHASE_5A_FOUNDATION | `PARTIAL_UNTIL_REVIEWED_SOURCE` |",
        "| REAL_MT_SEMANTIC_SOURCE_AVAILABLE | `SR2026_FUTURE_TEST_ONLY` |",
        "| REAL_MT_SEMANTIC_SOURCE_FOR_CURRENT_LIVE | `NO` |",
        "| SYNTHETIC_MT_SOURCE_AVAILABLE | `YES` |",
        "| RUNTIME_MT_ACTIVATIONS_FROM_PHASE_5A | `0` |",
        "",
        "The matrix below is the current-live lane. Authorised SR2026 Message Reference",
        "Guides were read in Phase 5B; that is a future-test lane and is reported "
        "separately in",
        "[mt-sr2026-semantic-readiness.md](mt-sr2026-semantic-readiness.md).",
        "",
        "## Matrix",
        "",
        "| Message | SRU | Structural source | Runtime installed | Semantic source | "
        "Source authority | Segmentation ready | Canonical reference ready | "
        "Candidate extraction ready | Reviewed base rules | Market rules | Client rules | "
        "Authoring readiness | Blocker |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(f"`{item}`" for item in row) + " |")
    lines += [
        "",
        "## Notes",
        "",
        "- Prowide remains build-time structural evidence only.",
        "- The synthetic MT source is an invented fixture for pipeline proof, not SWIFT "
        "authority.",
        "- No reviewed base, market or client MT semantic Rule Pack is installed by this "
        "phase.",
        "- Phase 4B candidate source models remain inactive.",
        "",
    ]
    return "\n".join(lines)


def render_source_readiness(manifest: SourceManifest | None = None) -> str:
    manifest = manifest or SourceManifest()
    real_sources = _real_mt_sources(manifest)
    synthetic_sources = _synthetic_mt_sources(manifest)
    formats = ", ".join(sorted({suffix for suffix in ADAPTER_BY_SUFFIX}))
    lines = [
        "# MT Semantic Source Readiness",
        "",
        "Generated by `make mt-rule-check`. This report describes configured source "
        "readiness only; it does not expose restricted source text.",
        "",
        "## Supported source formats",
        "",
        f"`{formats}`",
        "",
        "PDF support is text-layer only and depends on an optional local extractor. OCR is "
        "outside Phase 5A.",
        "",
        "## Configured drop points",
        "",
        "| Purpose | Location | Setting | Git policy |",
        "| --- | --- | --- | --- |",
        f"| Business-rule sources | `{_repo_relative(rule_source_directory())}` | "
        "`RULE_SOURCE_DIRECTORY` | raw non-synthetic sources ignored |",
        "",
        "## Discovered sources",
        "",
        "| Source | Type | Version | SRU | Messages | Redistribution | External model |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in [*synthetic_sources, *real_sources]:
        redistribution = (
            "source=yes excerpt=yes"
            if source.redistribution.source_may_be_committed
            and source.redistribution.excerpts_may_be_committed
            else "restricted"
        )
        model = "YES" if source.external_model_processing_allowed() else "BLOCKED"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{source.source_id}`",
                    f"`{source.source_type.value}`",
                    f"`{source.version}`",
                    f"`{source.standards_release or 'UNKNOWN'}`",
                    f"`{', '.join(source.message_identifiers) or '-'}`",
                    f"`{redistribution}`",
                    f"`{model}`",
                ]
            )
            + " |"
        )
    if not real_sources:
        lines.append(
            "| `NONE` | `REAL_AUTHORISED_MT_SEMANTIC_SOURCE` | `-` | `-` | `-` | "
            "`-` | `-` |"
        )
    lines += _mrg_section()
    lines += [
        "",
        "## Rejected or untrusted sources",
        "",
        "None found in configured source locations during this pass.",
        "",
        "## Operator action required",
        "",
        "Provide one of the following authorised MT semantic sources for the required SRU:",
        "",
        "- authorised SWIFT MT Standards/UHB material;",
        "- approved MyStandards export;",
        "- client implementation guide;",
        "- approved internal rule specification;",
        "- approved market or custodian guide.",
        "",
        "Preferred format: UTF-8 text or Markdown with exact SRU metadata. Acceptable "
        "formats: clean HTML and text-based PDF. Scanned PDF needs preprocessing outside "
        "Phase 5A.",
        "",
        "PHASE_5_REAL_SOURCE_READY = `SR2026_FUTURE_TEST` — an authorised SR2026 source is "
        "declared for MT540 and MT541. No authorised source exists for the current-live "
        "release, so current-live semantic readiness is unchanged.",
        "",
    ]
    return "\n".join(lines)


def _mrg_section() -> list[str]:
    """The Message Reference Guides an operator has declared, present or not.

    Declaration is committed; the documents are not. Reporting the declaration rather than
    the file makes this document identical on every machine, which is what lets it be
    checked by `make check` on a clean clone.
    """
    catalogue = MrgSourceCatalogue()
    if not catalogue.ids():
        return []
    lines = [
        "",
        "## Declared SWIFT Message Reference Guides",
        "",
        "Licensed documents. The declaration below is committed; the documents themselves "
        "are read from a local drop directory and never enter Git. See "
        "[../mt-real-semantic-phase-05b.md](../mt-real-semantic-phase-05b.md).",
        "",
        "| Source | Release | Messages | Document digest | Redistribution | External model |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source_id in catalogue.ids():
        bundle = catalogue.get(source_id)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{bundle.source_id}`",
                    f"`{bundle.standards_release or 'UNKNOWN'}`",
                    f"`{', '.join(bundle.message_identifiers) or '-'}`",
                    f"`{(bundle.source_checksum or 'NOT_DECLARED')[:23]}…`",
                    "`restricted`"
                    if not bundle.redistribution.source_may_be_committed
                    else "`source=yes`",
                    "`ALLOWED`"
                    if bundle.external_model_processing_allowed()
                    else "`BLOCKED`",
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def write_reports() -> None:
    SEMANTIC_READINESS_DOCUMENT.write_text(render_semantic_readiness(), encoding="utf-8")
    SOURCE_READINESS_DOCUMENT.write_text(render_source_readiness(), encoding="utf-8")


def check_reports() -> bool:
    return (
        SEMANTIC_READINESS_DOCUMENT.read_text(encoding="utf-8")
        == render_semantic_readiness()
        and SOURCE_READINESS_DOCUMENT.read_text(encoding="utf-8")
        == render_source_readiness()
    )


def _message(
    extraction: MtProwideExtraction, message_type: str
) -> MtMessageEvidence | None:
    wanted = message_type.upper()
    return next((item for item in extraction.messages if item.message_type == wanted), None)


def _sequence_path(
    message: MtMessageEvidence, sequence_path: str
) -> MtSequenceEvidence | None:
    wanted = sequence_path.upper()
    matches = [
        item
        for item in message.sequences
        if item.path.upper() == wanted or item.code.upper() == wanted
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _full_tag(
    request: MtSemanticReferenceRequest, log: RuleFindingLog
) -> str | None:
    tag = request.tag.upper()
    option = request.option.upper() if request.option else None
    match = _TAG.fullmatch(tag)
    if match is None:
        log.error(
            RuleFindingCode.MT_RULE_FIELD_NOT_FOUND,
            f"{request.tag} is not an MT tag.",
            "Use a two-digit tag with an optional lettered option.",
            subject=request.message_type,
            location=request.tag,
        )
        return None
    suffix = match.group("option") or None
    if option and suffix and suffix != option:
        log.error(
            RuleFindingCode.MT_RULE_OPTION_NOT_RESOLVED,
            f"{tag} carries option {suffix}, not {option}.",
            "Do not supply conflicting tag and option values.",
            subject=request.message_type,
            location=tag,
        )
        return None
    return tag if suffix or option is None else f"{tag}{option}"


def _resolved_option(tag: str, group: MtFieldGroupEvidence) -> str | None:
    option = tag.removeprefix(group.field_number)
    return option or None


def _component_ok(
    extraction: MtProwideExtraction, tag: str, component: int | None
) -> bool:
    if component is None:
        return True
    if component < 1:
        return False
    global_field = next((item for item in extraction.global_fields if item.tag == tag), None)
    return bool(
        global_field
        and global_field.components_size
        and component <= global_field.components_size
    )


def _runtime_field(
    index: StructureIndex,
    request: MtSemanticReferenceRequest,
    sequence_code: str,
    full_tag: str,
) -> tuple[FieldRef | None, str | None, str]:
    if not index.known(MessageFormat.MT, request.message_type):
        return None, None, "NO_RUNTIME_SPECIFICATION"
    ref = FieldRef(
        format=MessageFormat.MT,
        sequence_path=sequence_code,
        tag=full_tag,
        qualifier=request.qualifier,
    )
    resolved = index.resolve(ref, request.message_type)
    if resolved is None:
        return None, None, "UNRESOLVED"
    return FieldRef(format=MessageFormat.MT, field_id=resolved.key), resolved.key, "RESOLVED"


def _runtime_ambiguous(
    index: StructureIndex, message_type: str, sequence_code: str, full_tag: str
) -> bool:
    if not index.known(MessageFormat.MT, message_type):
        return False
    # A tag-only reference that fails while the same tag+known qualifiers exist is
    # ambiguous rather than absent.
    return (
        index.resolve(
            FieldRef(format=MessageFormat.MT, sequence_path=sequence_code, tag=full_tag),
            message_type,
        )
        is None
        and any(
            field.key.startswith(f"{message_type}-")
            and f"-{full_tag}-" in field.key
            for field in index.fields(MessageFormat.MT, message_type)
        )
    )


def _all_manifest_sources(manifest: SourceManifest) -> list[SourceBundle]:
    return [manifest.get(source_id) for source_id in manifest.ids()]


def _real_mt_sources(manifest: SourceManifest) -> list[SourceBundle]:
    return [
        source
        for source in _all_manifest_sources(manifest)
        if source.source_type in MT_SEMANTIC_SOURCE_TYPES
    ]


def _synthetic_mt_sources(manifest: SourceManifest) -> list[SourceBundle]:
    return [
        source
        for source in _all_manifest_sources(manifest)
        if source.source_type is RuleSourceType.SYNTHETIC_FIXTURE
        and (
            source.message_identifiers
            or source.applicable_message_categories
            or "MT" in source.source_id
        )
    ]


def _readiness_blocker(installed: bool, source_available: bool) -> str:
    if not installed:
        return "NO_RUNTIME_SPECIFICATION"
    if not source_available:
        return "REAL_SEMANTIC_SOURCE_MISSING"
    return "REVIEWED_RULE_PACK_MISSING"


def _repo_relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[3]
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return path.name
