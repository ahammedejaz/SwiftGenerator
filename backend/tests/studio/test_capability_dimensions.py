"""The dimensional capability model stays honest.

Structure, business rules, market practice, client profile and external validation are
separate claims with separate evidence. These tests pin the two properties that matter:
every value is derived from what actually exists, and the mere existence of the model
upgrades nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.specifications.registry import specification_registry
from app.studio.capability import (
    BusinessRuleStatus,
    ExternalValidationStatus,
    OverlayStatus,
    StructureStatus,
    capability_summary,
    derive_dimensions,
)
from app.studio.catalogue import capability_dimensions
from app.studio.models import MessageFormat
from app.studio.mx.registry import mx_registry

client = TestClient(app)

FORBIDDEN_CLAIMS = ("certified", "compliant", "production ready", "production-ready")


def test_no_existing_message_is_upgraded_by_the_model_existing() -> None:
    for spec in specification_registry.list():
        dims = capability_dimensions(MessageFormat.MT, spec.message_type)
        assert dims.structure is StructureStatus.CONFIGURED_SUBSET
        assert dims.market_practice is OverlayStatus.NOT_CONFIGURED
        assert dims.external_validation is ExternalValidationStatus.NOT_RUN
    for spec in mx_registry.all_specs():
        dims = capability_dimensions(MessageFormat.MX, spec.message_type)
        # Nothing in this repository was compiled from a schema; claiming so would be
        # exactly the false promotion the model exists to prevent.
        assert dims.structure is StructureStatus.CONFIGURED_SUBSET
        assert dims.external_validation is ExternalValidationStatus.NOT_RUN


def test_client_profile_dimension_is_measured_from_the_profiles() -> None:
    # Profiles declare required fields for the MT subset, so those messages read
    # CONFIGURED; nothing declares MX requirements today, so MX must not.
    assert (
        capability_dimensions(MessageFormat.MT, "MT541").client_profile
        is OverlayStatus.CONFIGURED
    )
    assert (
        capability_dimensions(MessageFormat.MX, "sese.023").client_profile
        is OverlayStatus.NOT_CONFIGURED
    )


def test_the_summary_never_makes_a_forbidden_claim() -> None:
    for spec in specification_registry.list():
        summary = capability_summary(
            capability_dimensions(MessageFormat.MT, spec.message_type)
        )
        lowered = summary.lower()
        assert not any(claim in lowered for claim in FORBIDDEN_CLAIMS), summary


def test_a_generated_pack_reads_compiled_not_hand_reviewed() -> None:
    dims = derive_dimensions(
        generated_from_schema=True,
        has_business_rules=False,
        profile_configured=False,
    )
    assert dims.structure is StructureStatus.COMPILED_FROM_SCHEMA
    assert dims.business_rules is BusinessRuleStatus.NOT_CONFIGURED
    summary = capability_summary(dims)
    assert "compiled from a source schema" in summary
    assert "Business rules are not configured." in summary


def test_dimensions_travel_on_spec_catalogue_and_coverage() -> None:
    spec = client.get("/api/v1/messages/MT541/spec").json()
    assert spec["capability"]["structure"] == "CONFIGURED_SUBSET"
    assert spec["capabilitySummary"]

    catalogue = client.get("/api/v1/catalogue").json()
    assert all(entry["capability"] is not None for entry in catalogue["messages"])

    coverage = client.get("/api/v1/coverage").json()
    for row in coverage["messages"]:
        assert row["capabilityDimensions"]["externalValidation"] == "NOT_RUN"
        # The legacy single word is untouched — additive, not a replacement.
        assert row["capability"] == "PARTIAL"
