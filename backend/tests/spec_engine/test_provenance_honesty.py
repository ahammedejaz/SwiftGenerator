"""An operator's provenance declaration must never become a compliance claim.

The platform can know that a schema arrived through the official-artifact drop location
and that the operator declared it official. It cannot independently prove the file is
the genuine ISO artifact — so that declaration may inform the *structure* dimension's
provenance and nothing else, and no wording anywhere may promote it to compliance.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.spec_engine.gates import validate_pack
from app.spec_engine.pipeline import compile_schema
from app.studio.capability import (
    BusinessRuleStatus,
    ExternalValidationStatus,
    OverlayStatus,
    StructureStatus,
    capability_summary,
    derive_dimensions,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "xsd" / "test.001.001.01.xsd"

FORBIDDEN_WORDING = (
    "swift compliant",
    "iso compliant",
    "certified",
    "production ready",
    "production-ready",
)


def test_declaring_a_source_official_upgrades_only_structure_provenance() -> None:
    pack = compile_schema(FIXTURE, source_type="OFFICIAL_ISO_20022_XSD")
    assert pack.spec.source.source_type == "OFFICIAL_ISO_20022_XSD"
    assert pack.spec.source.generated is True

    # The dimensions derive from what exists, and an official *declaration* changes
    # none of the rule/practice/profile/external dimensions.
    dimensions = derive_dimensions(
        generated_from_schema=pack.spec.source.generated,
        has_business_rules=bool(pack.spec.require_one_of),
        profile_configured=False,
    )
    assert dimensions.structure is StructureStatus.COMPILED_FROM_SCHEMA
    assert dimensions.business_rules is BusinessRuleStatus.NOT_CONFIGURED
    assert dimensions.market_practice is OverlayStatus.NOT_CONFIGURED
    assert dimensions.client_profile is OverlayStatus.NOT_CONFIGURED
    assert dimensions.external_validation is ExternalValidationStatus.NOT_RUN


def test_no_forbidden_wording_anywhere_in_the_official_path() -> None:
    pack = compile_schema(FIXTURE, source_type="OFFICIAL_ISO_20022_XSD")

    surfaces = [pack.yaml_text.lower()]
    surfaces.append(
        capability_summary(
            derive_dimensions(
                generated_from_schema=True,
                has_business_rules=False,
                profile_configured=False,
            )
        ).lower()
    )
    result = validate_pack(pack.yaml_text, pack.version, FIXTURE)
    surfaces.append(result.render().lower())
    for finding in [*pack.findings, *result.findings]:
        surfaces.append(finding.render().lower())

    for surface in surfaces:
        for phrase in FORBIDDEN_WORDING:
            assert phrase not in surface, phrase


def test_the_compiler_default_makes_no_official_claim() -> None:
    # Declaring a source official is an explicit operator statement. The default must
    # record no such claim — a silent default would convert omission into declaration.
    pack = compile_schema(FIXTURE)
    spec = yaml.safe_load(pack.yaml_text)
    assert spec["source"]["sourceType"] == "OPERATOR_SUPPLIED_XSD"


def test_the_official_validation_detail_names_the_operator_not_the_standard() -> None:
    # With no official schema dropped in, the derived path speaks for itself; the
    # OFFICIAL detail string is pinned at the source level instead so a rewording that
    # reintroduces an authority claim fails here.
    import inspect

    from app.studio.mx import xsd
    from app.studio.mx.registry import mx_registry
    from app.studio.mx.xsd import validate_document

    source = inspect.getsource(xsd)
    assert "operator-supplied official schema" in source

    spec = mx_registry.get("sese.023")
    outcome = validate_document(spec, "<not-xml")
    assert outcome.schema_source.value in {"SUBSET_DERIVED", "OFFICIAL"}
