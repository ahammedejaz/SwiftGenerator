from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.domain.models import ApiModel


class ArtifactRole(StrEnum):
    CORE_JAR = "core_jar"
    SOURCE_JAR = "source_jar"
    JAVA_PROBE_DEPENDENCY = "java_probe_dependency"


class EvidenceKind(StrEnum):
    PROWIDE_SOURCE_JAVADOC_SCHEME = "PROWIDE_SOURCE_JAVADOC_SCHEME"
    PROWIDE_FIELD_CLASS_REFLECTION = "PROWIDE_FIELD_CLASS_REFLECTION"
    PROWIDE_PARSER_ROUND_TRIP = "PROWIDE_PARSER_ROUND_TRIP"
    REPOSITORY_REVIEWED_CONFIGURATION = "REPOSITORY_REVIEWED_CONFIGURATION"


class Presence(StrEnum):
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    UNKNOWN = "UNKNOWN"


class SourceConfidence(StrEnum):
    OBSERVED = "OBSERVED"
    UNKNOWN = "UNKNOWN"
    NOT_PROMOTED = "NOT_PROMOTED"
    GLOBAL_ONLY = "GLOBAL_ONLY"


class CandidateStructureState(StrEnum):
    SOURCE_DISCOVERED = "SOURCE_DISCOVERED"
    STRUCTURE_EXTRACTED = "STRUCTURE_EXTRACTED"
    STRUCTURE_COMPILED = "STRUCTURE_COMPILED"
    CROSS_ENGINE_PARSED = "CROSS_ENGINE_PARSED"
    ROUNDTRIP_VERIFIED = "ROUNDTRIP_VERIFIED"
    AUTHORING_READY = "AUTHORING_READY"
    INSTALLED = "INSTALLED"


class AuthoringReadinessStatus(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED_REQUIREDNESS_UNKNOWN = "BLOCKED_REQUIREDNESS_UNKNOWN"
    BLOCKED_FIELD_USE_UNKNOWN = "BLOCKED_FIELD_USE_UNKNOWN"
    BLOCKED_QUALIFIER_RULES_UNKNOWN = "BLOCKED_QUALIFIER_RULES_UNKNOWN"
    STRUCTURAL_EVIDENCE_ONLY = "STRUCTURAL_EVIDENCE_ONLY"


class ProwideArtifact(ApiModel):
    role: ArtifactRole
    coordinate: str
    file_name: str
    url: str
    sha256: str
    maven_sha1: str | None = None


class SourceVerification(ApiModel):
    swift_standards_release_url: str
    maven_metadata_url: str
    maven_latest_observed: str
    maven_metadata_last_updated: str
    prowide_repository_url: str
    license: str


class ProwideSourceLock(ApiModel):
    schema_version: str
    source_name: str
    source_url: str
    documentation_url: str
    artifact_coordinate: str
    prowidesoftware_version: str
    swift_standards_release: str
    verified_at: str
    verification: SourceVerification
    artifacts: list[ProwideArtifact]


class MtSequenceEvidence(ApiModel):
    path: str
    code: str
    name: str
    parent_path: str | None = None
    order: int
    presence: Presence
    min_occurs: int
    max_occurs: int | None = None
    repeatable: bool
    source_text: str
    evidence: EvidenceKind = EvidenceKind.PROWIDE_SOURCE_JAVADOC_SCHEME


class MtFieldSetEvidence(ApiModel):
    id: str
    sequence_path: str
    parent_sequence_path: str | None = None
    field_number: str
    order: int
    presence: Presence
    min_occurs: int
    max_occurs: int | None = None
    repeatable: bool
    source_text: str
    evidence: EvidenceKind = EvidenceKind.PROWIDE_SOURCE_JAVADOC_SCHEME


class MtFieldGroupEvidence(ApiModel):
    id: str
    sequence_path: str
    fieldset_id: str | None = None
    order: int
    field_number: str
    options: list[str]
    tags: list[str]
    presence: Presence
    min_occurs: int
    max_occurs: int | None = None
    repeatable: bool
    source_text: str
    evidence: EvidenceKind = EvidenceKind.PROWIDE_SOURCE_JAVADOC_SCHEME
    qualifier_legality: SourceConfidence = SourceConfidence.UNKNOWN
    code_list_legality: SourceConfidence = SourceConfidence.UNKNOWN


class MtMessageEvidence(ApiModel):
    message_type: str
    base_message_type: str
    category: int
    source_model: str
    variant: str | None = None
    name: str
    package_name: str
    class_name: str
    source_path: str
    sru: int
    sequence_count: int
    fieldset_count: int
    field_group_count: int
    distinct_tags: list[str]
    sequences: list[MtSequenceEvidence] = Field(default_factory=list)
    fieldsets: list[MtFieldSetEvidence] = Field(default_factory=list)
    field_groups: list[MtFieldGroupEvidence] = Field(default_factory=list)
    structure_states: list[CandidateStructureState] = Field(
        default_factory=lambda: [
            CandidateStructureState.SOURCE_DISCOVERED,
            CandidateStructureState.STRUCTURE_EXTRACTED,
        ]
    )
    authoring_status: AuthoringReadinessStatus = (
        AuthoringReadinessStatus.STRUCTURAL_EVIDENCE_ONLY
    )
    authoring_blockers: list[str] = Field(default_factory=list)


class MtGlobalFieldEvidence(ApiModel):
    tag: str
    class_name: str
    sru: int | None = None
    types_pattern: str | None = None
    parser_pattern: str | None = None
    validator_pattern: str | None = None
    component_labels: list[str | None] = Field(default_factory=list)
    optional_components: list[int] = Field(default_factory=list)
    components_size: int | None = None
    generic: bool | None = None
    error: str | None = None
    evidence: EvidenceKind = EvidenceKind.PROWIDE_FIELD_CLASS_REFLECTION


class MtProwideExtraction(ApiModel):
    schema_version: str = "mt-prowide-extraction/2"
    source: ProwideSourceLock
    extracted_scope: str
    selected_message_count: int
    discovered_categories: list[int] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)
    messages: list[MtMessageEvidence]
    global_fields: list[MtGlobalFieldEvidence]
    activated_messages: list[str] = Field(default_factory=list)
    candidate_messages: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ProwideParsedTag(ApiModel):
    index: int
    tag: str
    value: str
    qualifier: str | None = None
    field_class: str | None = None


class MtProwideParseResult(ApiModel):
    evidence: EvidenceKind = EvidenceKind.PROWIDE_PARSER_ROUND_TRIP
    requested_message_type: str
    parsed_message_type: str
    sru: int | None
    tag_count: int
    tags: list[ProwideParsedTag]


class MtCrossEngineResult(ApiModel):
    message_type: str
    source_version: str
    tag_stream_identical: bool
    python_tag_count: int
    prowide_tag_count: int
    python_import_errors: int
    python_import_warnings: int
    prowide: MtProwideParseResult
