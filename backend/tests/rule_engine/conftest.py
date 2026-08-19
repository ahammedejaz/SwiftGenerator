"""Shared scaffolding for the rule-engine suites."""

from __future__ import annotations

from typing import Any

import pytest

from app.rule_engine.refs import FieldKind, FieldRef, ResolvedFieldRef, StructureIndex
from app.studio.models import MessageFormat, Presence

#: The configured sese.023 subset is the structure these suites bind against: it is real,
#: installed, and rich enough to have codes, dates, numbers, identifiers and optionality.
P = "/Document/SctiesSttlmTxInstr/"
TXID = P + "TxId"
MVMT = P + "SttlmTpAndAddtlParams/SctiesMvmntTp"
PMT = P + "SttlmTpAndAddtlParams/Pmt"
CMONID = P + "SttlmTpAndAddtlParams/CmonId"
TRADDT = P + "TradDtls/TradDt/Dt/Dt"
STTLMDT = P + "TradDtls/SttlmDt/Dt/Dt"
ISIN = P + "FinInstrmId/ISIN"
DESC = P + "FinInstrmId/Desc"
UNIT = P + "QtyAndAcctDtls/SttlmQty/Qty/Unit"
ACCT = P + "QtyAndAcctDtls/SfkpgAcct/Id"
TXTP = P + "SttlmParams/SctiesTxTp/Cd"
TXCOND = P + "SttlmParams/SttlmTxCond/Cd"
DLVRAGT = P + "DlvrgSttlmPties/Pty1/Id/AnyBIC"
RCVGAGT = P + "RcvgSttlmPties/Pty1/Id/AnyBIC"
AMT = P + "SttlmAmt/Amt"
CDTDBT = P + "SttlmAmt/CdtDbtInd"

MESSAGE = "sese.023"


def mx(path: str) -> FieldRef:
    return FieldRef(format=MessageFormat.MX, path=path)


def binding(
    path: str,
    kind: FieldKind = FieldKind.TEXT,
    *,
    max_occurs: int = 1,
    codes: tuple[str, ...] = (),
    presence: Presence = Presence.OPTIONAL,
    always_present: bool = False,
) -> ResolvedFieldRef:
    """A hand-made binding, for the DSL tests that exercise semantics rather than lookup."""
    return ResolvedFieldRef(
        canonical=f"MX|{path}",
        key=path,
        display_name=path.rsplit("/", 1)[-1],
        kind=kind,
        presence=presence,
        max_occurs=max_occurs,
        codes=codes,
        location=path,
        always_present=always_present,
    )


def bindings(*items: ResolvedFieldRef) -> dict[str, ResolvedFieldRef]:
    return {item.canonical: item for item in items}


@pytest.fixture(scope="session")
def index() -> StructureIndex:
    return StructureIndex()


def node(payload: dict[str, Any]) -> Any:
    """Validate a raw expression the way a YAML pack would deliver it."""
    from pydantic import TypeAdapter

    from app.rule_engine.dsl import Expression

    return TypeAdapter(Expression).validate_python(payload)


def evidence(source_id: str = "SYNTH-TEST-SOURCE", ordinal: int = 1) -> Any:
    """A well-formed evidence record. Hashes are of fixed text, so packs stay stable."""
    from app.rule_engine.models import Evidence
    from app.rule_engine.sources import sha256_of

    digest = sha256_of(f"{source_id}#{ordinal}")
    return Evidence(
        source_id=source_id,
        segment_id=f"{source_id}#S{ordinal:04d}",
        source_location="synthetic-test-source.md",
        source_version="1.0",
        source_checksum=sha256_of(source_id),
        segment_hash=digest,
        excerpt_hash=digest,
        heading="Test section",
        line_start=1,
        line_end=2,
    )


def source_reference(source_id: str = "SYNTH-TEST-SOURCE") -> Any:
    from app.rule_engine.models import RuleSourceType, SourceReference
    from app.rule_engine.sources import sha256_of

    return SourceReference(
        source_id=source_id,
        source_type=RuleSourceType.SYNTHETIC_FIXTURE,
        title="Synthetic source for the rule-engine suites",
        version="1.0",
        source_location="synthetic-test-source.md",
        source_checksum=sha256_of(source_id),
    )


def rule(
    rule_id: str,
    assertion: Any,
    *,
    when: Any = None,
    severity: Any = None,
    reviewed: bool = True,
    source_id: str = "SYNTH-TEST-SOURCE",
) -> Any:
    from app.rule_engine.models import (
        Rule,
        RuleFindingText,
        RuleReview,
        RuleReviewStatus,
    )
    from app.studio.models import IssueSeverity

    status = RuleReviewStatus.REVIEWED if reviewed else RuleReviewStatus.MACHINE_CHECKED
    return Rule(
        rule_id=rule_id,
        title=f"Test rule {rule_id}",
        severity=severity or IssueSeverity.ERROR,
        when=when,
        assert_=assertion,
        finding=RuleFindingText(
            message=f"The message does not satisfy {rule_id}.",
            suggestion="Correct the message and try again.",
        ),
        evidence=(evidence(source_id),),
        review=RuleReview(
            status=status, reviewed_by="Test reviewer" if reviewed else "",
            reviewed_at="SOURCE_CONTROLLED" if reviewed else "NOT_REVIEWED",
        ),
    )


def restriction(
    restriction_id: str,
    path: str,
    codes: tuple[str, ...],
    *,
    reviewed: bool = True,
    source_id: str = "SYNTH-TEST-SOURCE",
) -> Any:
    from app.rule_engine.models import (
        CodeRestriction,
        RuleFindingText,
        RuleReview,
        RuleReviewStatus,
    )

    status = RuleReviewStatus.REVIEWED if reviewed else RuleReviewStatus.MACHINE_CHECKED
    return CodeRestriction(
        restriction_id=restriction_id,
        field=mx(path),
        codes=codes,
        finding=RuleFindingText(
            message=f"Only {', '.join(codes)} may be used here.",
            suggestion=f"Choose one of {', '.join(codes)}.",
        ),
        evidence=(evidence(source_id),),
        review=RuleReview(
            status=status, reviewed_by="Test reviewer" if reviewed else "",
            reviewed_at="SOURCE_CONTROLLED" if reviewed else "NOT_REVIEWED",
        ),
    )


def pack(
    index: StructureIndex,
    *,
    layer: Any = None,
    profile_id: str | None = None,
    rules: tuple[Any, ...] = (),
    restrictions: tuple[Any, ...] = (),
    reviewed: bool = True,
    message_type: str = MESSAGE,
    pack_version: str = "v1",
    structure_checksum: str | None = None,
    source_ids: tuple[str, ...] = ("SYNTH-TEST-SOURCE",),
) -> Any:
    from app.knowledge.models import RuleLayer
    from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
    from app.rule_engine.compiler import structure_compatibility_for
    from app.rule_engine.models import (
        RulePack,
        RuleReview,
        RuleReviewStatus,
        StructureCompatibility,
    )

    resolved_layer = layer or RuleLayer.BASE_STANDARD
    compatibility = structure_compatibility_for(index, MessageFormat.MX, message_type)
    if structure_checksum is not None:
        compatibility = StructureCompatibility(
            structure_version=compatibility.structure_version,
            structure_checksum=structure_checksum,
        )
    version = index.version(MessageFormat.MX, message_type)
    parts = [MessageFormat.MX.value, version or message_type, resolved_layer.value]
    if profile_id:
        parts.append(profile_id)
    parts.append(pack_version)
    status = RuleReviewStatus.REVIEWED if reviewed else RuleReviewStatus.REVIEW_REQUIRED
    return RulePack(
        pack_id=":".join(parts),
        format=MessageFormat.MX,
        message_type=message_type,
        message_version=version,
        layer=resolved_layer,
        profile_id=profile_id,
        pack_version=pack_version,
        title=f"Test pack for {message_type}",
        engine_version=RULE_ENGINE_VERSION,
        dsl_version=DSL_VERSION,
        structure_compatibility=compatibility,
        review=RuleReview(
            status=status, reviewed_by="Test reviewer" if reviewed else "",
            reviewed_at="SOURCE_CONTROLLED" if reviewed else "NOT_REVIEWED",
        ),
        sources=tuple(source_reference(item) for item in source_ids),
        rules=rules,
        code_restrictions=restrictions,
    )
