"""Mapping evidence classes, candidate previews, relationships and the new operators.

Nothing here needs the operator's knowledge base: the packs are validated as YAML, the
relationships are listed from the registry, and the transforms are exercised directly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.mapping.models import (
    MappingEvidenceClass,
    MappingIdentity,
    MappingKind,
    MappingOutput,
    MappingPack,
    MappingReviewState,
    MappingRule,
    TransformName,
)
from app.mapping.registry import MappingRegistry
from app.mapping.service import MappingError, MappingService
from app.studio.models import Lane, MessageFormat


def test_every_committed_pack_declares_its_evidence_class_honestly() -> None:
    registry = MappingRegistry()
    classes = {pack.pack_id: pack.provenance.evidence_class for pack in registry.packs}
    assert classes["SYNTHETIC_MT541_TO_SESE023_V1"] is MappingEvidenceClass.SYNTHETIC
    assert classes["CANDIDATE_MT202_TO_PACS009_V1"] is MappingEvidenceClass.TARGET_RELATIONSHIP_ONLY
    assert classes["CANDIDATE_MT103_TO_PACS008_V1"] is MappingEvidenceClass.NAME_CORRESPONDENCE
    # No pack claims more than the knowledge base supports, and none is production eligible.
    assert all(
        pack.provenance.evidence_class is not MappingEvidenceClass.SOURCE_BACKED
        for pack in registry.packs
    )
    assert not any(pack.provenance.production_eligible for pack in registry.packs)
    for pack in registry.packs:
        if pack.provenance.review_state is MappingReviewState.CANDIDATE_PREVIEW:
            assert pack.cited_rule_count == len(pack.rules), pack.pack_id
            assert pack.provenance.relationship_citations, pack.pack_id


def test_relationships_are_listed_with_their_evidence_and_cover_the_named_messages() -> None:
    registry = MappingRegistry()
    ids = {item.relationship_id for item in registry.relationships}
    assert "MT20X-FI-CREDIT-TRANSFER-PACS009" in ids
    source = MappingIdentity(
        format=MessageFormat.MT, message_type="MT202", release="SR2026", lane=Lane.KNOWLEDGE_PREVIEW
    )
    found = registry.relationships_for(source)
    assert [item.relationship_id for item in found] == ["MT20X-FI-CREDIT-TRANSFER-PACS009"]
    assert found[0].evidence_class is MappingEvidenceClass.TARGET_RELATIONSHIP_ONLY
    assert any(
        cite.source_id == "SWIFT-MT-SR2026-MT205-MRG" and cite.page == 4
        for cite in found[0].citations
    )
    targets = MappingService(registry).targets(source)
    pack_targets = [item for item in targets.targets if item.pack_id]
    assert (
        pack_targets
        and pack_targets[0].evidence_class is MappingEvidenceClass.TARGET_RELATIONSHIP_ONLY
    )
    assert pack_targets[0].preview_only and not pack_targets[0].production_eligible
    # A relationship without a pack is listed as not convertible, with its evidence.
    mt104 = MappingIdentity(
        format=MessageFormat.MT, message_type="MT104", release="SR2026", lane=Lane.KNOWLEDGE_PREVIEW
    )
    listed = MappingService(registry).targets(mt104).targets
    assert listed and listed[0].pack_id is None and not listed[0].convertible
    assert listed[0].relationship is not None and listed[0].relationship.blocker


def _pack(**overrides):  # type: ignore[no-untyped-def]
    base = dict(
        packId="T",
        version="1.0.0",
        source={
            "format": "MT",
            "messageType": "MT202",
            "release": "SR2026",
            "lane": "KNOWLEDGE_PREVIEW",
        },
        target={
            "format": "MX",
            "messageType": "pacs.009",
            "release": "pacs.009.001.13",
            "lane": "KNOWLEDGE_PREVIEW",
        },
        sourceStructureChecksum="0" * 64,
        targetStructureChecksum="0" * 64,
        provenance={
            "sourceType": "TEST",
            "sourceReference": "x.md",
            "sourceChecksum": "0" * 64,
            "reviewState": "CANDIDATE_PREVIEW",
            "evidenceClass": "TARGET_RELATIONSHIP_ONLY",
            "relationshipCitations": [{"sourceId": "S"}],
        },
        rules=[
            {"id": "r", "kind": "DIRECT", "sourceRefs": ["A"], "outputs": [{"targetRef": "/D/x"}]}
        ],
    )
    base.update(overrides)
    return base


def test_source_backed_requires_every_rule_to_be_cited() -> None:
    provenance = _pack()["provenance"] | {
        "evidenceClass": "SOURCE_BACKED",
        "reviewState": "REVIEWED",
        "reviewedBy": "x",
    }
    with pytest.raises(ValidationError, match="cite every rule"):
        MappingPack.model_validate(_pack(provenance=provenance))
    cited = _pack(provenance=provenance)
    cited["rules"][0]["citations"] = [{"sourceId": "S", "page": 3}]
    assert MappingPack.model_validate(cited).cited_rule_count == 1


def test_name_correspondence_and_synthetic_can_never_be_reviewed_or_eligible() -> None:
    provenance = _pack()["provenance"] | {
        "evidenceClass": "NAME_CORRESPONDENCE",
        "reviewState": "REVIEWED",
        "reviewedBy": "x",
    }
    with pytest.raises(ValidationError, match="cannot be REVIEWED"):
        MappingPack.model_validate(_pack(provenance=provenance))
    provenance = _pack()["provenance"] | {"productionEligible": True}
    with pytest.raises(ValidationError):
        MappingPack.model_validate(_pack(provenance=provenance))


def test_operator_kinds_are_enforced_against_rule_shape() -> None:
    with pytest.raises(ValidationError, match="ENUM"):
        MappingRule.model_validate(
            {"id": "c", "kind": "CODE_MAP", "sourceRefs": ["A"], "outputs": [{"targetRef": "/x"}]}
        )
    with pytest.raises(ValidationError, match="unchanged"):
        MappingRule.model_validate(
            {
                "id": "d",
                "kind": "DIRECT",
                "sourceRefs": ["A"],
                "outputs": [{"targetRef": "/x", "transform": "MT_DATE_TO_ISO"}],
            }
        )
    omit = MappingRule.model_validate({"id": "o", "kind": "OMIT", "sourceRefs": ["A"]})
    assert omit.kind is MappingKind.OMIT and not omit.outputs


@pytest.mark.parametrize(
    ("transform", "value", "expected"),
    [
        (TransformName.MT_DATED_AMOUNT_DATE, "260818USD1000,", "2026-08-18"),
        (TransformName.MT_DATED_AMOUNT_TO_ISO, "260818USD1000,", "USD 1000"),
        (TransformName.MT_DATED_AMOUNT_TO_ISO, "260818EUR1234,56", "EUR 1234.56"),
        (TransformName.MT_AMOUNT_TO_ISO, "USD1000,", "USD 1000"),
        (TransformName.MT_PARTY_BIC, "/C/12345\nDEMOGB2LXXX", "DEMOGB2LXXX"),
        (TransformName.MT_PARTY_BIC, "DEMOGB2L", "DEMOGB2L"),
    ],
)
def test_new_transforms_are_deterministic(
    transform: TransformName, value: str, expected: str
) -> None:
    output = MappingOutput(target_ref="/x", transform=transform)
    assert MappingService._transform(output, [value], " ") == expected


def test_new_transforms_refuse_malformed_input() -> None:
    with pytest.raises(MappingError):
        MappingService._transform(
            MappingOutput(target_ref="/x", transform=TransformName.MT_DATED_AMOUNT_DATE),
            ["USD1000,"],
            " ",
        )
    with pytest.raises(MappingError):
        MappingService._transform(
            MappingOutput(target_ref="/x", transform=TransformName.MT_PARTY_BIC), ["not a bic"], " "
        )
