"""The Rule Pack: versioned, reviewed, evidence-backed configuration.

A pack says what a *valid use* of an already-valid structure looks like. It never says
what the structure is — that authority stays with the structure pack, and nothing here can
reach it.

Naming follows the repository rather than inventing a parallel vocabulary: the layer is the
existing :class:`app.knowledge.models.RuleLayer` (``BASE_STANDARD`` / ``MARKET_PRACTICE`` /
``CLIENT_PROFILE``), which is also how the layers map onto ``ValidationLayer``.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum

from pydantic import Field, model_validator

from app.knowledge.models import RuleLayer
from app.rule_engine.dsl import Expression
from app.rule_engine.refs import FieldRef, RuleModel
from app.studio.models import IssueSeverity, MessageFormat

#: The layers a rule pack may occupy. ``INTERNAL_RULE_PACK`` exists on the knowledge
#: records for a different purpose and is not a rule-pack layer.
PACK_LAYERS = (RuleLayer.BASE_STANDARD, RuleLayer.MARKET_PRACTICE, RuleLayer.CLIENT_PROFILE)
#: Layers that narrow a layer beneath them and therefore must name the profile they serve.
OVERLAY_LAYERS = (RuleLayer.MARKET_PRACTICE, RuleLayer.CLIENT_PROFILE)

RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$")
SOURCE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$")
SEGMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]*#S\d{4}$")
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PACK_VERSION_PATTERN = re.compile(r"^v\d+$")
PROFILE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

#: An excerpt is a reviewer convenience, never a redistribution channel.
MAX_EXCERPT_CHARS = 400


class RuleSourceType(StrEnum):
    """What the operator declares a source document to be.

    A declaration, not a verification. The platform can know a file arrived through the
    configured drop directory and that the operator labelled it; it cannot prove the file
    is the genuine licensed artifact, and no wording anywhere may turn the label into a
    compliance claim.
    """

    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    OPERATOR_SUPPLIED_GUIDELINE = "OPERATOR_SUPPLIED_GUIDELINE"
    OPERATOR_SUPPLIED_MARKET_PRACTICE = "OPERATOR_SUPPLIED_MARKET_PRACTICE"
    OPERATOR_SUPPLIED_CLIENT_GUIDELINE = "OPERATOR_SUPPLIED_CLIENT_GUIDELINE"
    OFFICIAL_ISO_20022_MESSAGE_DEFINITION_REPORT = (
        "OFFICIAL_ISO_20022_MESSAGE_DEFINITION_REPORT"
    )
    OFFICIAL_ISO_20022_MESSAGE_USAGE_GUIDE = "OFFICIAL_ISO_20022_MESSAGE_USAGE_GUIDE"


class RuleReviewStatus(StrEnum):
    """The candidate lifecycle. Only ``REVIEWED`` is ever loaded at runtime."""

    AI_CANDIDATE = "AI_CANDIDATE"
    MACHINE_CHECKED = "MACHINE_CHECKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ExtractionMethod(StrEnum):
    #: Two isolated passes over the same evidence. Deliberately not called "independent":
    #: the passes may share provider, model family and training data.
    ISOLATED_DUAL_EXTRACTION = "ISOLATED_DUAL_EXTRACTION"
    HAND_AUTHORED = "HAND_AUTHORED"


class ExtractionAgreement(StrEnum):
    AGREE = "AGREE"
    PARTIAL_AGREEMENT = "PARTIAL_AGREEMENT"
    CONFLICT = "CONFLICT"
    ONLY_A = "ONLY_A"
    ONLY_B = "ONLY_B"
    NO_RULE = "NO_RULE"


class Evidence(RuleModel):
    """Where a rule came from, precisely enough for a reviewer to go and read it."""

    source_id: str = Field(alias="sourceId", max_length=64)
    segment_id: str = Field(alias="segmentId", max_length=80)
    source_location: str = Field(alias="sourceLocation", max_length=200)
    source_version: str = Field(alias="sourceVersion", max_length=64)
    source_checksum: str = Field(alias="sourceChecksum")
    segment_hash: str = Field(alias="segmentHash")
    excerpt_hash: str = Field(alias="excerptHash")
    #: Present only where the operator declared excerpts redistributable.
    excerpt: str | None = Field(default=None, max_length=MAX_EXCERPT_CHARS)
    heading: str | None = Field(default=None, max_length=200)
    page: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, alias="lineStart", ge=1)
    line_end: int | None = Field(default=None, alias="lineEnd", ge=1)

    @model_validator(mode="after")
    def check_identity(self) -> Evidence:
        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise ValueError(f"Not a source id: {self.source_id}")
        if not SEGMENT_ID_PATTERN.fullmatch(self.segment_id):
            raise ValueError(f"Not a segment id: {self.segment_id}")
        if not self.segment_id.startswith(self.source_id + "#"):
            raise ValueError(f"{self.segment_id} does not belong to {self.source_id}")
        for name, value in (
            ("sourceChecksum", self.source_checksum),
            ("segmentHash", self.segment_hash),
            ("excerptHash", self.excerpt_hash),
        ):
            if not CHECKSUM_PATTERN.fullmatch(value):
                raise ValueError(f"{name} must be sha256:<64 hex characters>")
        if self.line_start and self.line_end and self.line_end < self.line_start:
            raise ValueError("lineEnd precedes lineStart")
        return self


class RuleFindingText(RuleModel):
    """Prose with zero authority: never parsed, never able to change an outcome."""

    message: str = Field(min_length=8, max_length=300)
    suggestion: str = Field(min_length=8, max_length=300)


class RuleReview(RuleModel):
    status: RuleReviewStatus
    reviewed_by: str = Field(default="", alias="reviewedBy", max_length=120)
    #: No clock in a committed file: the commit is the timestamp. Mirrors the
    #: ``reviewedAt: NOT_REVIEWED`` convention the MX packs already use.
    reviewed_at: str = Field(default="NOT_REVIEWED", alias="reviewedAt", max_length=64)
    candidate_hash: str | None = Field(default=None, alias="candidateHash")
    rule_hash: str | None = Field(default=None, alias="ruleHash")
    rejection_reason: str | None = Field(
        default=None, alias="rejectionReason", max_length=300
    )

    @model_validator(mode="after")
    def check_reviewed_named(self) -> RuleReview:
        if self.status is RuleReviewStatus.REVIEWED and not self.reviewed_by.strip():
            raise ValueError("A reviewed rule must name its reviewer")
        for name, value in (
            ("candidateHash", self.candidate_hash),
            ("ruleHash", self.rule_hash),
        ):
            if value is not None and not CHECKSUM_PATTERN.fullmatch(value):
                raise ValueError(f"{name} must be sha256:<64 hex characters>")
        return self


class ExtractionMetadata(RuleModel):
    """How a model-proposed rule was produced. Absent on hand-authored rules."""

    method: ExtractionMethod
    agreement: ExtractionAgreement
    extractor_models: tuple[str, ...] = Field(default=(), alias="extractorModels")
    refuter_model: str | None = Field(default=None, alias="refuterModel")
    prompt_version: str = Field(default="", alias="promptVersion", max_length=64)
    schema_version: str = Field(default="", alias="schemaVersion", max_length=64)
    #: The refuter's structured criticism, kept so a later reader sees what was objected
    #: to. Never chain-of-thought: only the closed schema's fields are persisted.
    refuter_objections: tuple[str, ...] = Field(default=(), alias="refuterObjections")


class Rule(RuleModel):
    rule_id: str = Field(alias="ruleId", max_length=80)
    title: str = Field(min_length=4, max_length=140)
    severity: IssueSeverity = IssueSeverity.ERROR
    #: Absent means unconditional.
    when: Expression | None = None
    assert_: Expression = Field(alias="assert")
    finding: RuleFindingText
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    review: RuleReview
    extraction: ExtractionMetadata | None = None

    @model_validator(mode="after")
    def check_identity(self) -> Rule:
        if not RULE_ID_PATTERN.fullmatch(self.rule_id):
            raise ValueError(
                f"{self.rule_id} is not a rule id: use upper-case words joined by hyphens"
            )
        return self

    def canonical_body(self) -> str:
        """A stable serialisation of everything that decides the rule's behaviour.

        Presentation and review metadata are excluded on purpose: rewording a message or
        recording a different reviewer must not change the rule's identity.
        """
        payload = {
            "ruleId": self.rule_id,
            "severity": self.severity.value,
            "when": self.when.model_dump(mode="json", by_alias=True, exclude_defaults=True)
            if self.when
            else None,
            "assert": self.assert_.model_dump(
                mode="json", by_alias=True, exclude_defaults=True
            ),
            "evidence": [
                {
                    "sourceId": item.source_id,
                    "segmentId": item.segment_id,
                    "segmentHash": item.segment_hash,
                }
                for item in self.evidence
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def body_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_body().encode("utf-8")).hexdigest()


class CodeRestriction(RuleModel):
    """An overlay narrowing the code values a field may carry.

    First class rather than expressed as an ``IN`` rule, because narrowing has to be
    *compared across layers* — that is the only way to refuse a higher layer that widens a
    lower one instead of narrowing it.
    """

    restriction_id: str = Field(alias="restrictionId", max_length=80)
    field: FieldRef
    codes: tuple[str, ...] = Field(min_length=1)
    finding: RuleFindingText
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    review: RuleReview
    severity: IssueSeverity = IssueSeverity.ERROR
    extraction: ExtractionMetadata | None = None

    @model_validator(mode="after")
    def check_codes(self) -> CodeRestriction:
        if not RULE_ID_PATTERN.fullmatch(self.restriction_id):
            raise ValueError(f"{self.restriction_id} is not a restriction id")
        if len(set(self.codes)) != len(self.codes):
            raise ValueError(f"{self.restriction_id} lists a code twice")
        return self

    def canonical_body(self) -> str:
        payload = {
            "restrictionId": self.restriction_id,
            "field": self.field.canonical(),
            "codes": sorted(self.codes),
            "severity": self.severity.value,
            "evidence": [
                {
                    "sourceId": item.source_id,
                    "segmentId": item.segment_id,
                    "segmentHash": item.segment_hash,
                }
                for item in self.evidence
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def body_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_body().encode("utf-8")).hexdigest()


class StructureCompatibility(RuleModel):
    structure_version: str = Field(alias="structureVersion", max_length=64)
    structure_checksum: str = Field(alias="structureChecksum")

    @model_validator(mode="after")
    def check_checksum(self) -> StructureCompatibility:
        if not CHECKSUM_PATTERN.fullmatch(self.structure_checksum):
            raise ValueError("structureChecksum must be sha256:<64 hex characters>")
        return self


class SourceReference(RuleModel):
    """The derived metadata a pack may carry about a source. Never the source itself."""

    source_id: str = Field(alias="sourceId", max_length=64)
    source_type: RuleSourceType = Field(alias="sourceType")
    title: str = Field(max_length=200)
    version: str = Field(max_length=64)
    source_location: str = Field(alias="sourceLocation", max_length=200)
    source_checksum: str = Field(alias="sourceChecksum")
    excerpts_may_be_committed: bool = Field(default=False, alias="excerptsMayBeCommitted")

    @model_validator(mode="after")
    def check_identity(self) -> SourceReference:
        if not SOURCE_ID_PATTERN.fullmatch(self.source_id):
            raise ValueError(f"Not a source id: {self.source_id}")
        if not CHECKSUM_PATTERN.fullmatch(self.source_checksum):
            raise ValueError("sourceChecksum must be sha256:<64 hex characters>")
        return self


class RulePack(RuleModel):
    pack_id: str = Field(alias="packId", max_length=160)
    format: MessageFormat
    message_type: str = Field(alias="messageType", min_length=3, max_length=32)
    #: The full versioned identity where the format has one (MX). ``None`` for MT.
    message_version: str | None = Field(default=None, alias="messageVersion", max_length=32)
    layer: RuleLayer
    #: Required on an overlay layer; forbidden on the base layer.
    profile_id: str | None = Field(default=None, alias="profileId", max_length=64)
    pack_version: str = Field(alias="packVersion", max_length=16)
    title: str = Field(min_length=4, max_length=200)
    engine_version: str = Field(alias="engineVersion", max_length=32)
    dsl_version: str = Field(alias="dslVersion", max_length=32)
    structure_compatibility: StructureCompatibility = Field(alias="structureCompatibility")
    review: RuleReview
    sources: tuple[SourceReference, ...] = Field(default=())
    #: Never true in this phase: a rule pack derived from evidence establishes what the
    #: evidence says, not that the evidence covers the standard.
    authoritative_completeness_known: bool = Field(
        default=False, alias="authoritativeCompletenessKnown"
    )
    limitations: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()
    code_restrictions: tuple[CodeRestriction, ...] = Field(
        default=(), alias="codeRestrictions"
    )

    @model_validator(mode="after")
    def check_pack(self) -> RulePack:
        if self.layer not in PACK_LAYERS:
            raise ValueError(f"{self.layer} is not a rule-pack layer")
        if self.layer in OVERLAY_LAYERS and not self.profile_id:
            raise ValueError(f"A {self.layer} pack must name the profile it serves")
        if self.layer is RuleLayer.BASE_STANDARD and self.profile_id:
            raise ValueError("A base pack applies to every profile and must not name one")
        if self.profile_id and not PROFILE_ID_PATTERN.fullmatch(self.profile_id):
            raise ValueError(f"Not a profile id: {self.profile_id}")
        if not PACK_VERSION_PATTERN.fullmatch(self.pack_version):
            raise ValueError(f"packVersion must look like v1, not {self.pack_version}")
        if self.format is MessageFormat.MX and not self.message_version:
            raise ValueError("An MX rule pack must name the message version it targets")
        if self.format is MessageFormat.MT and self.message_version:
            raise ValueError("MT messages have no version identity; omit messageVersion")
        if not self.rules and not self.code_restrictions:
            raise ValueError(f"{self.pack_id} declares nothing")
        if self.authoritative_completeness_known:
            raise ValueError(
                "A rule pack establishes what its evidence says, never that the evidence "
                "is complete; authoritativeCompletenessKnown must remain false"
            )
        expected = self.expected_pack_id()
        if self.pack_id != expected:
            raise ValueError(f"packId must be {expected}, not {self.pack_id}")
        declared = {item.source_id for item in self.sources}
        holders: list[Rule | CodeRestriction] = [*self.rules, *self.code_restrictions]
        referenced = {
            evidence.source_id for holder in holders for evidence in holder.evidence
        }
        missing = sorted(referenced - declared)
        if missing:
            raise ValueError(f"Evidence names undeclared sources: {', '.join(missing)}")
        return self

    def expected_pack_id(self) -> str:
        identity = self.message_version or self.message_type
        parts = [self.format.value, identity, self.layer.value]
        if self.profile_id:
            parts.append(self.profile_id)
        parts.append(self.pack_version)
        return ":".join(parts)

    def file_name(self) -> str:
        return self.pack_id.replace(":", "_").lower() + ".yaml"

    def all_reviews(self) -> list[RuleReview]:
        return [
            self.review,
            *(item.review for item in self.rules),
            *(item.review for item in self.code_restrictions),
        ]

    def fully_reviewed(self) -> bool:
        return all(item.status is RuleReviewStatus.REVIEWED for item in self.all_reviews())
