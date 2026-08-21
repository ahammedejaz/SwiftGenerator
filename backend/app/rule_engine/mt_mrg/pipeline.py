"""Reading one guide end to end: declare, ingest, classify, discover, translate, compile.

The order is the point. Nothing is read until the operator has declared the document and
the bytes have matched the declaration; nothing is translated until the section headings
have said which pages carry rules; nothing is compiled until every reference has resolved
against the structure the same guide states. A step that cannot complete stops the ones
after it rather than handing them a guess.

Every candidate this produces leaves ``REVIEW_REQUIRED``. Machine checks establish that a
candidate is *well formed* — its references resolve, its expression compiles, its source
rule and error code are recorded — and that is a different claim from the candidate being
*right*, which only somebody who can read the named page can make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT, get_settings, source_path
from app.knowledge.models import RuleLayer
from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
from app.rule_engine.compiler import CompiledRulePack, compile_pack
from app.rule_engine.diagnostics import RuleEngineError, RuleFinding
from app.rule_engine.models import (
    Evidence,
    ExtractionAgreement,
    ExtractionMetadata,
    ExtractionMethod,
    Rule,
    RuleFindingText,
    RulePack,
    RuleReview,
    RuleReviewStatus,
    SourceReference,
    StructureCompatibility,
)
from app.rule_engine.mt_mrg import MRG_READER_VERSION
from app.rule_engine.mt_mrg.document import (
    MrgIdentity,
    MrgPage,
    MrgSection,
    MrgSectionSpan,
    classify,
    identify,
    missing_sections,
    pages_of,
    section_of_segment,
)
from app.rule_engine.mt_mrg.formatspec import MrgStructure, StructureBuilder
from app.rule_engine.mt_mrg.rules import (
    MrgSourceRule,
    RuleFidelity,
    RuleTranslation,
    discover,
    numbering_is_contiguous,
)
from app.rule_engine.mt_mrg.structure import MrgStructureIndex
from app.rule_engine.mt_mrg.templates import translate
from app.rule_engine.sources import (
    IngestedSource,
    Segment,
    SourceBundle,
    ingest,
    normalise,
    sha256_of,
)
from app.studio.models import IssueSeverity, MessageFormat

#: The committed declaration of the Message Reference Guides this repository knows about.
#: Metadata only — identity, release, expected digest, redistribution posture. The document
#: bodies live wherever the operator dropped them and are never committed.
MRG_MANIFEST_NAME = "mt-mrg-sources.yaml"


def mrg_manifest_path() -> Path:
    return source_path(get_settings().rule_source_directory, "rule_sources") / MRG_MANIFEST_NAME


#: The drop directory a clean clone assumes when nothing is configured. Ignored by Git and
#: usually empty, which is the normal state: the guides are licensed and most checkouts of
#: this repository will never hold one.
DEFAULT_MRG_DIRECTORY_NAME = "swiftKnowledgeBase"


def mrg_source_directory() -> Path:
    """Where the operator dropped the guides.

    Configured rather than hard-coded, because the path is one person's machine and the
    repository must not carry it. ``MT_MRG_SOURCE_DIRECTORY`` points at the drop; unset
    means the ignored directory beside the checkout that the documentation names.
    """
    configured = get_settings().mt_mrg_source_directory
    if configured.strip():
        return source_path(configured)
    return PROJECT_ROOT / DEFAULT_MRG_DIRECTORY_NAME


class MrgSourceCatalogue:
    """The declared guides. Absent is normal — a clean clone has none of them."""

    def __init__(self, path: Path | None = None, directory: Path | None = None) -> None:
        self._path = path or mrg_manifest_path()
        self._directory = directory or mrg_source_directory()
        self._bundles = self._load()

    def _load(self) -> dict[str, SourceBundle]:
        if not self._path.is_file():
            return {}
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        bundles: dict[str, SourceBundle] = {}
        for entry in raw.get("sources") or []:
            bundle = SourceBundle.model_validate(entry)
            if bundle.source_id in bundles:
                raise ValueError(f"Duplicate source id: {bundle.source_id}")
            bundles[bundle.source_id] = bundle
        return bundles

    @property
    def directory(self) -> Path:
        return self._directory

    def ids(self) -> list[str]:
        return sorted(self._bundles)

    def get(self, source_id: str) -> SourceBundle:
        try:
            return self._bundles[source_id.strip().upper()]
        except KeyError as error:
            raise KeyError(f"Unknown Message Reference Guide: {source_id}") from error

    def present(self, source_id: str) -> bool:
        bundle = self.get(source_id)
        return (self._directory / bundle.source_location).is_file()

    def ingest(self, source_id: str) -> IngestedSource:
        """Read one guide through the ordinary source pipeline, not a special one."""
        return ingest(self.get(source_id), self._directory)


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentClassification:
    segment_id: str
    section: MrgSection
    page: int | None
    heading: str | None
    segment_hash: str
    characters: int


@dataclass(frozen=True)
class RuleObjection:
    """A deterministic criticism of one translated rule, raised from the source itself.

    The guide cross-references its own rules: every qualifier table carries a ``CR`` column
    naming the Network Validated Rules that govern that qualifier. Comparing that column
    against what a translation claims to target is a refutation the document itself
    supplies — no second opinion, no model, and no way for the two to agree by having made
    the same mistake.
    """

    source_rule_id: str
    code: str
    detail: str


@dataclass
class MrgReading:
    """Everything one guide yielded, and everything that stopped it yielding more."""

    source_id: str
    identity: MrgIdentity
    checksum: str
    page_count: int
    pages: tuple[MrgPage, ...]
    spans: tuple[MrgSectionSpan, ...]
    segments: tuple[Segment, ...]
    classifications: tuple[SegmentClassification, ...]
    structure: MrgStructure
    rules: tuple[MrgSourceRule, ...]
    translations: tuple[RuleTranslation, ...]
    objections: tuple[RuleObjection, ...]
    problems: tuple[str, ...] = ()
    compiled: CompiledRulePack | None = None
    compile_findings: tuple[RuleFinding, ...] = ()
    pack: RulePack | None = None
    index: MrgStructureIndex | None = None

    def by_fidelity(self, fidelity: RuleFidelity) -> tuple[RuleTranslation, ...]:
        return tuple(item for item in self.translations if item.fidelity is fidelity)

    def translation(self, source_rule_id: str) -> RuleTranslation | None:
        return next(
            (
                item
                for item in self.translations
                if item.rule.source_rule_id == source_rule_id
            ),
            None,
        )

    def metrics(self) -> dict[str, object]:
        return {
            "sourceId": self.source_id,
            "messageType": self.identity.message_type,
            "standardsRelease": self.identity.standards_release,
            "pageCount": self.page_count,
            "segments": len(self.segments),
            "sequences": len(self.structure.sequences),
            "formatRows": len(self.structure.rows),
            "fieldSpecifications": len(self.structure.field_specs),
            "qualifierRows": sum(len(item.qualifiers) for item in self.structure.field_specs),
            "networkValidatedRules": len(self.rules),
            "exact": len(self.by_fidelity(RuleFidelity.EXACT)),
            "partial": len(self.by_fidelity(RuleFidelity.PARTIAL)),
            "unsupported": len(self.by_fidelity(RuleFidelity.UNSUPPORTED)),
            "notRecognised": len(self.by_fidelity(RuleFidelity.NOT_RECOGNISED)),
            "objections": len(self.objections),
            "candidateRules": len(self.pack.rules) if self.pack else 0,
            "structureChecksum": self.structure.checksum(),
            "liveModelCalls": 0,
        }


def read_guide(ingested: IngestedSource, directory: Path | None = None) -> MrgReading:
    """Read one ingested guide into structure, rules and candidate translations."""
    text = normalise(_marked_text(ingested, directory or mrg_source_directory()))
    pages = pages_of(text)
    identity, problems = identify(pages)
    if identity is None:
        raise ValueError(
            f"{ingested.bundle.source_id} does not read as a Message Reference Guide: "
            + ", ".join(problems)
        )
    declared = ingested.bundle
    trouble: list[str] = []
    if declared.standards_release and declared.standards_release != identity.standards_release:
        trouble.append(
            f"DECLARED_RELEASE_{declared.standards_release}_BUT_DOCUMENT_SAYS_"
            f"{identity.standards_release}"
        )
    if declared.message_identifiers and identity.message_type not in declared.message_identifiers:
        trouble.append(
            f"DECLARED_MESSAGES_{'_'.join(declared.message_identifiers)}_BUT_DOCUMENT_IS_"
            f"{identity.message_type}"
        )
    if trouble:
        # A renamed or mis-declared file is exactly how one message's rules end up
        # attributed to another, so the document's own words win and the run stops.
        raise ValueError(f"{declared.source_id}: " + ", ".join(trouble))

    spans = classify(pages, identity.message_type)
    absent = missing_sections(spans)
    structure = StructureBuilder(
        identity.message_type, identity.standards_release
    ).build(
        pages,
        spans,
        message_name=identity.message_name,
        release_text=identity.release_cover_text,
    )
    rules = discover(
        pages,
        spans,
        message_type=identity.message_type,
        message_name=identity.message_name,
        standards_release=identity.standards_release,
        release_text=identity.release_cover_text,
    )
    translations = tuple(translate(item, structure) for item in rules)
    classifications = tuple(
        SegmentClassification(
            segment_id=segment.segment_id,
            section=section_of_segment(spans, segment),
            page=segment.page,
            heading=segment.heading,
            segment_hash=segment.segment_hash,
            characters=len(segment.text),
        )
        for segment in ingested.segments
    )
    problems_found = [
        *(f"SECTION_MISSING_{item.value}" for item in absent),
        *structure.problems,
    ]
    if not numbering_is_contiguous(rules):
        problems_found.append("NETWORK_VALIDATED_RULE_NUMBERING_NOT_CONTIGUOUS")
    return MrgReading(
        source_id=declared.source_id,
        identity=identity,
        checksum=ingested.checksum,
        page_count=ingested.page_count,
        pages=pages,
        spans=spans,
        segments=ingested.segments,
        classifications=classifications,
        structure=structure,
        rules=rules,
        translations=translations,
        objections=refute(translations, structure),
        problems=tuple(problems_found),
    )


def _marked_text(ingested: IngestedSource, directory: Path) -> str:
    """Re-read the source bytes into page-marked text.

    ``ingest`` already proved the document readable, checksummed it and segmented it; this
    reads the same bytes through the same adapter to recover page boundaries, which
    segmentation deliberately discards. It is the same loader, not a second one.
    """
    from app.rule_engine.diagnostics import RuleFindingLog
    from app.rule_engine.sources import SourceAdapter, _pdf_to_text, resolve_within

    log = RuleFindingLog()
    path = resolve_within(directory, ingested.bundle.source_location, log)
    if path is None:
        raise RuleEngineError(log.findings)
    if ingested.adapter is not SourceAdapter.PDF_TEXT:
        return path.read_text(encoding="utf-8")
    extracted = _pdf_to_text(path.read_bytes(), ingested.bundle.source_location, log)
    if extracted is None:
        raise RuleEngineError(log.findings)
    return extracted[0]


# --------------------------------------------------------------------------------------
# Refutation
# --------------------------------------------------------------------------------------


def refute(
    translations: tuple[RuleTranslation, ...], structure: MrgStructure
) -> tuple[RuleObjection, ...]:
    """Check each translation against the guide's own cross-references.

    Two directions, both worth having:

    ``TARGET_NOT_CROSS_REFERENCED``
        the translation binds a qualifier whose table does not list this rule. Either the
        rule reaches further than the guide says it does, or the qualifier table is not the
        one the reader thinks it is. Both need a person.
    ``CROSS_REFERENCE_NOT_TARGETED``
        a qualifier's table names this rule and the translation never mentions that
        qualifier. The translation is narrower than the guide says the rule is.
    """
    objections: list[RuleObjection] = []
    claimed: dict[str, set[str]] = {}
    for spec in structure.field_specs:
        for qualifier in spec.qualifiers:
            for name in qualifier.conditional_rules:
                identity = f"{qualifier.sequence_path}:{qualifier.tag[:2]}:{qualifier.qualifier}"
                claimed.setdefault(name, set()).add(identity)

    for translation in translations:
        rule_id = translation.rule.source_rule_id
        expected = claimed.get(rule_id, set())
        if not expected:
            continue
        targeted = {
            f"{item.sequence_path}:{item.field_number}:{item.qualifier}"
            for item in translation.references
            if item.qualifier
        }
        for extra in sorted(targeted - expected):
            objections.append(
                RuleObjection(
                    source_rule_id=rule_id,
                    code="TARGET_NOT_CROSS_REFERENCED",
                    detail=(
                        f"{extra} is bound by this reading of {rule_id}, but that "
                        "qualifier's own table does not list the rule."
                    ),
                )
            )
        for missing in sorted(expected - targeted):
            objections.append(
                RuleObjection(
                    source_rule_id=rule_id,
                    code="CROSS_REFERENCE_NOT_TARGETED",
                    detail=(
                        f"{missing} names {rule_id} in its conditional-rule column, but "
                        "this reading of the rule does not bind it."
                    ),
                )
            )
    return tuple(objections)


# --------------------------------------------------------------------------------------
# Candidate compilation
# --------------------------------------------------------------------------------------

#: Fidelities that may become a candidate rule. ``PARTIAL`` qualifies because it is
#: *weaker* than the source and therefore cannot reject a message the source accepts;
#: the clause it drops travels with it as a limitation a reviewer must read.
CANDIDATE_FIDELITIES = (RuleFidelity.EXACT, RuleFidelity.PARTIAL)
#: A translation's residual marker for a rule the structure pack enforces on its own.
STRUCTURE_ENFORCED = "ENFORCED_BY_STRUCTURE"


def candidate_rule_id(translation: RuleTranslation) -> str:
    return translation.rule.canonical_rule_id


def _evidence(
    reading: MrgReading, translation: RuleTranslation, bundle: SourceBundle
) -> Evidence:
    """Where the rule is, precisely enough to open the page — and nothing more.

    The excerpt is deliberately absent and the segment hash deliberately present: a
    reviewer who has the document can find the rule from the page and the rule number,
    and a reader who does not have it learns nothing they were not licensed to learn.
    """
    rule = translation.rule
    segment = next(
        (
            item
            for item in reading.segments
            if item.line_start <= rule.first_line <= item.line_end
        ),
        reading.segments[0],
    )
    return Evidence(
        source_id=bundle.source_id,
        segment_id=segment.segment_id,
        source_location=bundle.source_location,
        source_version=bundle.version,
        source_checksum=reading.checksum,
        segment_hash=segment.segment_hash,
        excerpt_hash=rule.text_hash,
        excerpt=None,
        heading=(
            f"{reading.identity.message_type} Network Validated Rules — "
            f"{rule.source_rule_id}"
        ),
        page=rule.first_page,
        line_start=rule.first_line,
        line_end=rule.last_line,
    )


def _finding_text(translation: RuleTranslation) -> RuleFindingText:
    """Wording a tester could act on, derived from the expression rather than the book."""
    interpretation = translation.interpretation or "This source rule is not satisfied."
    return RuleFindingText(
        message=interpretation[:300],
        suggestion=(
            f"Check the message against {translation.rule.message_type} "
            f"{translation.rule.source_rule_id} "
            f"({', '.join(translation.rule.error_codes) or 'no error code stated'}) in the "
            f"{translation.rule.standards_release} Message Reference Guide, page "
            f"{translation.rule.first_page}."
        )[:300],
    )


def build_candidate_pack(reading: MrgReading, bundle: SourceBundle) -> RulePack | None:
    """Assemble the candidate pack. Every rule in it stays ``REVIEW_REQUIRED``."""
    index = MrgStructureIndex(reading.structure)
    rules: list[Rule] = []
    for translation in reading.translations:
        if translation.fidelity not in CANDIDATE_FIDELITIES or translation.assertion is None:
            continue
        if STRUCTURE_ENFORCED in translation.residual:
            continue  # exact by construction: the structure validator already enforces it
        objections = tuple(
            item.detail
            for item in reading.objections
            if item.source_rule_id == translation.rule.source_rule_id
        )
        rules.append(
            Rule(
                rule_id=candidate_rule_id(translation),
                title=(
                    f"{translation.rule.message_type} {translation.rule.source_rule_id} — "
                    f"{translation.template.replace('_', ' ').lower()}"
                )[:140],
                severity=IssueSeverity.ERROR,
                when=translation.when,
                assert_=translation.assertion,
                finding=_finding_text(translation),
                evidence=(_evidence(reading, translation, bundle),),
                review=RuleReview(status=RuleReviewStatus.REVIEW_REQUIRED),
                extraction=ExtractionMetadata(
                    method=ExtractionMethod.HAND_AUTHORED,
                    agreement=ExtractionAgreement.AGREE,
                    prompt_version=MRG_READER_VERSION,
                    schema_version=DSL_VERSION,
                    refuter_objections=(
                        *objections,
                        *(
                            f"{translation.rule.source_rule_id}: {item}"
                            for item in translation.residual
                        ),
                    ),
                ),
            )
        )
    if not rules:
        return None
    return RulePack(
        pack_id=(
            f"MT:{reading.identity.message_type}:{RuleLayer.BASE_STANDARD.value}:v1"
        ),
        format=MessageFormat.MT,
        message_type=reading.identity.message_type,
        layer=RuleLayer.BASE_STANDARD,
        pack_version="v1",
        title=(
            f"{reading.identity.message_type} {reading.identity.standards_release} "
            "Network Validated Rules — candidate, review required"
        ),
        engine_version=RULE_ENGINE_VERSION,
        dsl_version=DSL_VERSION,
        structure_compatibility=StructureCompatibility(
            structure_version=reading.identity.standards_release,
            structure_checksum=index.structure_checksum(
                MessageFormat.MT, reading.identity.message_type
            ),
        ),
        review=RuleReview(status=RuleReviewStatus.REVIEW_REQUIRED),
        sources=(
            SourceReference(
                source_id=bundle.source_id,
                source_type=bundle.source_type,
                title=bundle.title,
                version=bundle.version,
                source_location=bundle.source_location,
                source_checksum=reading.checksum,
                excerpts_may_be_committed=bundle.redistribution.excerpts_may_be_committed,
                standards_release=reading.identity.standards_release,
                applicable_message_categories=bundle.applicable_message_categories,
                message_identifiers=(reading.identity.message_type,),
                source_allows_external_model_processing=(
                    bundle.source_allows_external_model_processing
                ),
                provider_approved_for_source_classification=(
                    bundle.provider_approved_for_source_classification
                ),
            ),
        ),
        limitations=_limitations(reading),
        rules=tuple(rules),
    )


def _limitations(reading: MrgReading) -> tuple[str, ...]:
    limitations = [
        f"Derived from the {reading.identity.standards_release} Message Reference Guide, "
        "which is future-test material until that release goes live. Nothing here applies "
        "to the current-live release.",
        "Every rule is REVIEW_REQUIRED. Machine checks establish that a candidate is well "
        "formed, never that it is correct.",
        "Candidate rules are compiled against the structure the guide itself states, not "
        "against the installed runtime structure, and are not loadable by the runtime "
        "registry.",
    ]
    unsupported = reading.by_fidelity(RuleFidelity.UNSUPPORTED)
    if unsupported:
        limitations.append(
            f"{len(unsupported)} source rule(s) are not represented at all: "
            + ", ".join(item.rule.source_rule_id for item in unsupported)
            + "."
        )
    partial = reading.by_fidelity(RuleFidelity.PARTIAL)
    if partial:
        limitations.append(
            f"{len(partial)} rule(s) are represented more weakly than the source states "
            "them, so they can miss a violation but never invent one: "
            + ", ".join(item.rule.source_rule_id for item in partial)
            + "."
        )
    return tuple(limitations)


def compile_candidates(reading: MrgReading) -> MrgReading:
    """Compile the candidate pack through the ordinary compiler and record what it said."""
    bundle_free = reading
    index = MrgStructureIndex(reading.structure)
    reading.index = index
    if reading.pack is None:
        return bundle_free
    try:
        reading.compiled = compile_pack(reading.pack, index)
        reading.compile_findings = reading.compiled.warnings
    except RuleEngineError as error:
        reading.compiled = None
        reading.compile_findings = tuple(error.findings)
    return reading


@dataclass
class MrgRun:
    """One pass over every declared guide that is actually present."""

    readings: list[MrgReading] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    #: Guides that are present but could not be read, with the reason. A PDF with no text
    #: extractor installed is the ordinary case, and it is a condition to report rather
    #: than an exception to raise: everything derived from the guides is already committed,
    #: and only re-reading them is unavailable.
    unreadable: list[tuple[str, str]] = field(default_factory=list)

    def reading(self, message_type: str) -> MrgReading | None:
        return next(
            (
                item
                for item in self.readings
                if item.identity.message_type == message_type.upper()
            ),
            None,
        )


def run(catalogue: MrgSourceCatalogue | None = None) -> MrgRun:
    """Read every declared guide that is present. Absent guides are reported, not fatal."""
    catalogue = catalogue or MrgSourceCatalogue()
    outcome = MrgRun()
    for source_id in catalogue.ids():
        if not catalogue.present(source_id):
            outcome.missing.append(source_id)
            continue
        try:
            ingested = catalogue.ingest(source_id)
            reading = read_guide(ingested, catalogue.directory)
        except RuleEngineError as error:
            outcome.unreadable.append(
                (source_id, "; ".join(item.render() for item in error.findings))
            )
            continue
        reading.pack = build_candidate_pack(reading, ingested.bundle)
        outcome.readings.append(compile_candidates(reading))
    return outcome


def source_fingerprint(reading: MrgReading) -> str:
    """A digest binding a candidate to the exact bytes and structure it came from."""
    parts = [
        reading.source_id,
        reading.checksum,
        reading.identity.standards_release,
        reading.identity.message_type,
        reading.structure.checksum(),
        MRG_READER_VERSION,
    ]
    return sha256_of("|".join(parts))
