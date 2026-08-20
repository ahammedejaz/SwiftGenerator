"""Authoritative-source readiness: where a licensed artifact goes, and what it changes.

Every claim this platform makes about coverage is bounded by what it can read. Four classes
of artifact would move that boundary, and none of them may be reproduced, scraped or
approximated here — they are licensed. What *can* be prepared is the receiving end: a named
location, a setting that points at it, a loader that reads it without a code change, and an
honest statement of what is currently there.

That is what this module reports. It is deliberately a description of the platform's own
configuration, not an assessment of any artifact's content: an ``.xsd`` that appears in the
drop directory is reported as present, and the schema itself then does the judging.
"""

from __future__ import annotations

from enum import StrEnum

from app.config import get_settings, source_path
from app.domain.models import ApiModel
from app.profiles.loader import profiles
from app.rule_engine.models import RuleSourceType
from app.rule_engine.sources import SourceManifest, rule_source_directory
from app.specifications.registry import specification_registry
from app.studio.mx.registry import mx_registry
from app.studio.mx.xsd import official_schema_directory, official_schema_path


class SourceState(StrEnum):
    #: An authorised artifact is present and is what the platform reads.
    AUTHORITATIVE = "AUTHORITATIVE"
    #: The platform is running on configuration committed to this repository instead.
    REPOSITORY_CONFIGURED = "REPOSITORY_CONFIGURED"
    #: Nothing is present and nothing stands in for it.
    ABSENT = "ABSENT"


class SourceReadiness(ApiModel):
    id: str
    name: str
    #: What the artifact is, in the words a person licensing it would use.
    describes: str
    #: Where to put it.
    location: str
    #: The setting that points somewhere else, when the drop lives outside the checkout.
    setting: str
    state: SourceState
    #: What is being read right now.
    present: str
    #: What changes the moment an authorised artifact is in place.
    unlocks: list[str]


class SourceReadinessReport(ApiModel):
    sources: list[SourceReadiness]
    #: True only when every class above is AUTHORITATIVE.
    fully_sourced: bool


def build_readiness() -> SourceReadinessReport:
    settings = get_settings()
    mx_specs = mx_registry.all_specs()
    with_official = [spec for spec in mx_specs if official_schema_path(spec) is not None]
    unverified = [
        spec.message_type
        for spec in mx_specs
        if any("UNVERIFIED" in item for item in spec.limitations)
    ]
    profile_ids = sorted(item.profile_id for item in profiles.list())
    mt_specs = specification_registry.list()
    rule_sources = SourceManifest()
    real_mt_semantic = [
        rule_sources.get(source_id)
        for source_id in rule_sources.ids()
        if rule_sources.get(source_id).source_type
        in {
            RuleSourceType.OPERATOR_SUPPLIED_MT_GUIDE,
            RuleSourceType.OPERATOR_SUPPLIED_MYSTANDARDS_EXPORT,
            RuleSourceType.OPERATOR_SUPPLIED_INTERNAL_RULE_SOURCE,
            RuleSourceType.OPERATOR_SUPPLIED_CLIENT_GUIDELINE,
            RuleSourceType.OFFICIAL_SWIFT_MT_STANDARDS_MATERIAL,
            RuleSourceType.OFFICIAL_ISO_15022_DOCUMENTATION,
        }
    ]
    synthetic_mt_semantic = [
        rule_sources.get(source_id)
        for source_id in rule_sources.ids()
        if rule_sources.get(source_id).source_type is RuleSourceType.SYNTHETIC_FIXTURE
        and (
            rule_sources.get(source_id).message_identifiers
            or "MT" in rule_sources.get(source_id).source_id
        )
    ]

    sources = [
        SourceReadiness(
            id="ISO20022_OFFICIAL_XSD",
            name="Official ISO 20022 schemas",
            describes=(
                "The published .xsd for each message definition, named after its version — "
                "for example sese.023.001.11.xsd."
            ),
            location=str(official_schema_directory()),
            setting="MX_OFFICIAL_XSD_DIRECTORY",
            state=(
                SourceState.AUTHORITATIVE
                if len(with_official) == len(mx_specs)
                else SourceState.REPOSITORY_CONFIGURED
            ),
            present=(
                f"{len(with_official)} of {len(mx_specs)} configured messages have an "
                "official schema; the rest validate against a schema derived from this "
                "repository's own YAML."
            ),
            unlocks=[
                "The XSD validation layer reports OFFICIAL instead of SUBSET_DERIVED.",
                "Schema conformance becomes a real claim rather than internal consistency.",
            ],
        ),
        SourceReadiness(
            id="ISO20022_MESSAGE_DEFINITIONS",
            name="ISO 20022 message definition reports",
            describes=(
                "The approved message-definition report, or metadata derived from it, "
                "giving each message its version, root element and full element set."
            ),
            location=str(source_path(settings.mx_specification_directory, "mx")),
            setting="MX_SPECIFICATION_DIRECTORY",
            state=SourceState.REPOSITORY_CONFIGURED,
            present=(
                f"{len(mx_specs)} repository-configured subsets"
                + (
                    f", of which {len(unverified)} ({', '.join(unverified)}) have not been "
                    "reconciled against any message-definition report at all."
                    if unverified
                    else "."
                )
            ),
            unlocks=[
                "authoritativeCompletenessKnown can become true for a reconciled message.",
                "The UNVERIFIED limitation can be removed from a reconciled message.",
                "A capability above PARTIAL becomes arguable.",
            ],
        ),
        SourceReadiness(
            id="ISO15022_MT_SPECIFICATION",
            name="Licensed SWIFT MT specification",
            describes=(
                "The release-specific ISO 15022 format rows, sequences, qualifiers, code "
                "lists, usage rules and network validated rules."
            ),
            location=str(
                source_path(
                    settings.mt_specification_manifest,
                    "specifications",
                    "supported_subset_v1.yaml",
                )
            ),
            setting="MT_SPECIFICATION_MANIFEST",
            state=SourceState.REPOSITORY_CONFIGURED,
            present=(
                f"{len(mt_specs)} messages and "
                f"{sum(len(item.fields) for item in mt_specs)} rows, all "
                f"{specification_registry.registry_version}."
            ),
            unlocks=[
                "A real denominator, so coverage stops being subset-relative.",
                "Network validated rules and usage rules become enforceable.",
                "The 22F::SETR sequence placement question can be settled.",
            ],
        ),
        SourceReadiness(
            id="CLIENT_MYSTANDARDS_PROFILES",
            name="Client MyStandards usage guidelines",
            describes=(
                "A counterparty's own restrictions: permitted codes, mandatory optional "
                "fields, reference formats and envelope values."
            ),
            location=str(source_path(settings.client_profile_directory, "profiles")),
            setting="CLIENT_PROFILE_DIRECTORY",
            state=SourceState.REPOSITORY_CONFIGURED,
            present=(
                f"{len(profile_ids)} demonstration profile"
                f"{'' if len(profile_ids) == 1 else 's'} "
                f"({', '.join(profile_ids)}); none derived from a client guideline."
            ),
            unlocks=[
                "CLIENT_PROFILE validation reflects a real counterparty.",
                "Envelope values stop being demonstration placeholders.",
            ],
        ),
        SourceReadiness(
            id="MT_SEMANTIC_RULE_SOURCES",
            name="MT semantic business-rule sources",
            describes=(
                "Authorised MT standards material, MyStandards exports, market guides, "
                "client implementation guides or internal rule specifications used to "
                "derive reviewed MT Rule Packs."
            ),
            location=str(rule_source_directory()),
            setting="RULE_SOURCE_DIRECTORY",
            state=SourceState.ABSENT if not real_mt_semantic else SourceState.REPOSITORY_CONFIGURED,
            present=(
                f"{len(real_mt_semantic)} authorised MT semantic source(s) declared; "
                f"{len(synthetic_mt_semantic)} synthetic MT fixture(s) available for "
                "pipeline tests."
            ),
            unlocks=[
                "MT candidate Rule Packs can be extracted from legitimate evidence.",
                "Reviewed MT business, market or client rules can be installed through PRs.",
                "Business-rule readiness can move independently from structure readiness.",
            ],
        ),
    ]
    return SourceReadinessReport(
        sources=sources,
        fully_sourced=all(item.state is SourceState.AUTHORITATIVE for item in sources),
    )
