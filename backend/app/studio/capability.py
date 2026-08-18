"""The dimensional capability model: what is actually established about a message.

One word — ``PARTIAL`` — cannot answer the questions a delivery lead asks: is the
structure trustworthy, are business rules configured, is a market practice applied, has
anything external confirmed it? Each of those is a separate claim with separate evidence,
so each is a separate dimension. A message may be structure-verified against a schema and
still have no business rules; collapsing that into one badge would either overclaim the
rules or underclaim the structure.

Every value here is **derived from what exists** — provenance, configured rules, profile
requirements — never declared by a flag, following the same principle as the measured
coverage report. The legacy per-message ``capability: PARTIAL`` field is untouched;
these dimensions sit alongside it.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.models import ApiModel


class StructureStatus(StrEnum):
    #: Hand-authored repository subset, reviewed against public documentation.
    CONFIGURED_SUBSET = "CONFIGURED_SUBSET"
    #: Machine-compiled from a schema and validated against that schema at compile time.
    #: Whether the schema was the official artifact is a provenance fact (`sourceType`,
    #: `sourceChecksum`), not something this dimension can certify.
    COMPILED_FROM_SCHEMA = "COMPILED_FROM_SCHEMA"
    UNVERIFIED = "UNVERIFIED"


class BusinessRuleStatus(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    #: Cross-field rules exist for this message in the configured subset.
    CONFIGURED_SUBSET = "CONFIGURED_SUBSET"
    #: Reserved for Phase 2: rules extracted from an authoritative source with evidence.
    SOURCE_DERIVED = "SOURCE_DERIVED"
    REVIEWED = "REVIEWED"


class OverlayStatus(StrEnum):
    """Market-practice and client-profile layers share one vocabulary."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    CONFIGURED = "CONFIGURED"
    VERIFIED = "VERIFIED"


class ExternalValidationStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"


class CapabilityDimensions(ApiModel):
    structure: StructureStatus
    business_rules: BusinessRuleStatus
    market_practice: OverlayStatus
    client_profile: OverlayStatus
    external_validation: ExternalValidationStatus


#: The sentence fragments the summary is assembled from. Deliberately never "compliant",
#: "certified" or "production ready" — those claims need evidence this platform does not
#: hold.
_STRUCTURE_TEXT = {
    StructureStatus.CONFIGURED_SUBSET: (
        "Structure is the repository-configured subset."
    ),
    StructureStatus.COMPILED_FROM_SCHEMA: (
        "Structure was compiled from a source schema and validated against it."
    ),
    StructureStatus.UNVERIFIED: "Structure is unverified.",
}

_RULES_TEXT = {
    BusinessRuleStatus.NOT_CONFIGURED: "Business rules are not configured.",
    BusinessRuleStatus.CONFIGURED_SUBSET: (
        "Business rules cover the configured subset only."
    ),
    BusinessRuleStatus.SOURCE_DERIVED: (
        "Business rules were derived from a named source and await review."
    ),
    BusinessRuleStatus.REVIEWED: "Business rules have been reviewed.",
}


def capability_summary(dimensions: CapabilityDimensions) -> str:
    """One plain-language statement a non-specialist can act on."""
    parts = [
        _STRUCTURE_TEXT[dimensions.structure],
        _RULES_TEXT[dimensions.business_rules],
    ]
    if dimensions.market_practice is OverlayStatus.NOT_CONFIGURED:
        readiness = "Ready for structural testing"
    else:
        readiness = "Ready for market-practice testing"
    if dimensions.client_profile is not OverlayStatus.NOT_CONFIGURED:
        readiness += " under the configured client profiles"
    parts.append(readiness + "; no external validation has been run."
                 if dimensions.external_validation is ExternalValidationStatus.NOT_RUN
                 else readiness + ".")
    return " ".join(parts)


def derive_dimensions(
    *,
    generated_from_schema: bool,
    has_business_rules: bool,
    profile_configured: bool,
) -> CapabilityDimensions:
    """Derive the dimensions from what demonstrably exists.

    ``generated_from_schema`` comes from the pack's provenance (`source.generated`);
    ``has_business_rules`` from whether any cross-field rule names the message;
    ``profile_configured`` from whether any client profile declares requirements for it.
    Market practice and external validation have no configured sources yet, so they are
    reported as absent rather than assumed — no existing message is upgraded by the mere
    existence of this model.
    """
    return CapabilityDimensions(
        structure=(
            StructureStatus.COMPILED_FROM_SCHEMA
            if generated_from_schema
            else StructureStatus.CONFIGURED_SUBSET
        ),
        business_rules=(
            BusinessRuleStatus.CONFIGURED_SUBSET
            if has_business_rules
            else BusinessRuleStatus.NOT_CONFIGURED
        ),
        market_practice=OverlayStatus.NOT_CONFIGURED,
        client_profile=(
            OverlayStatus.CONFIGURED if profile_configured else OverlayStatus.NOT_CONFIGURED
        ),
        external_validation=ExternalValidationStatus.NOT_RUN,
    )
