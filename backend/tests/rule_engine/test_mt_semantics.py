"""Phase 5A MT semantic-rule ingestion boundaries.

The tests here deliberately use synthetic sources and temporary rule directories. They
prove the MT path can ingest, validate and load reviewed rules without turning Phase 4B
structural discovery into runtime semantic authority.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.knowledge.models import RuleLayer
from app.rule_engine import DSL_VERSION, RULE_ENGINE_VERSION
from app.rule_engine.compiler import structure_compatibility_for
from app.rule_engine.diagnostics import RuleFindingCode
from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.extraction.cache import ExtractionCache
from app.rule_engine.extraction.pipeline import RuleExtractionPipeline
from app.rule_engine.extraction.provider import ExtractionModels, ScriptedCompletionClient
from app.rule_engine.extraction.review import pack_yaml
from app.rule_engine.models import (
    Rule,
    RuleFindingText,
    RulePack,
    RuleReview,
    RuleReviewStatus,
    RuleSourceType,
)
from app.rule_engine.mt_semantics import (
    SEMANTIC_READINESS_DOCUMENT,
    SOURCE_READINESS_DOCUMENT,
    MtSemanticReferenceRequest,
    render_semantic_readiness,
    render_source_readiness,
    resolve_mt_semantic_reference,
)
from app.rule_engine.refs import FieldRef, StructureIndex
from app.rule_engine.sources import (
    IngestedSource,
    Redistribution,
    SourceAdapter,
    SourceBundle,
    SourceManifest,
    normalise,
    segment_text,
    sha256_of,
)
from app.spec_engine.mt_prowide.extractor import load_extraction
from app.spec_engine.mt_prowide.models import MtProwideExtraction
from app.studio.models import MessageFormat

BACKEND = Path(__file__).resolve().parents[2]
SYNTHETIC_MT_SOURCE = "SYNTH-MT-SEMANTIC-V1"
DEMO_PROFILE = "DEMO_MARKET_CLIENT_V1"
PLAIN_PROFILE = "BASE_DEMO_V1"

_MT_RUNTIME_PROBE = """
import json

from fastapi.testclient import TestClient

from app.main import app


def fields_without_or_with_reag(sample, reag):
    values = {item["id"]: dict(item) for item in sample["inputs"]}
    values["MT541-E-22F-SETR"]["value"] = "TRAD"
    values.pop("MT541-E-95P-REAG", None)
    if reag is not None:
        values["MT541-E-95P-REAG"] = {
            "id": "MT541-E-95P-REAG",
            "sequence": "SETDET",
            "occurrence": 1,
            "tag": "95P",
            "qualifier": "REAG",
            "option": "P",
            "value": reag,
        }
    return list(values.values())


def generate(client, fields, profile):
    return client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MT",
            "messageType": "MT541",
            "profileId": profile,
            "fields": fields,
            "persist": False,
        },
    ).json()


out = {}
with TestClient(app) as client:
    sample = client.get("/api/v1/messages/MT541/samples?format=MT").json()[-1]
    missing = fields_without_or_with_reag(sample, None)
    broken = generate(client, missing, "DEMO_MARKET_CLIENT_V1")
    issue = next(
        (
            item
            for item in broken["validation"]["errors"]
            if item["ruleId"] == "SYNTH-MT-CLIENT-REAG-FOR-TRAD"
        ),
        None,
    )
    fixed = generate(
        client,
        fields_without_or_with_reag(sample, "DEMOREAGXXX"),
        "DEMO_MARKET_CLIENT_V1",
    )
    plain = generate(client, missing, "BASE_DEMO_V1")
    intelligence = client.get(
        "/api/v1/intelligence/field",
        params={"id": "MT541-E-95P-REAG", "format": "MT"},
    ).json()
    out = {
        "brokenValid": broken["validation"]["valid"],
        "issue": issue,
        "fixedValid": fixed["validation"]["valid"],
        "plainValid": plain["validation"]["valid"],
        "plainRuleIds": [
            item["ruleId"] for item in plain["validation"]["errors"]
        ],
        "intelligenceRules": [
            item["ruleId"] for item in intelligence["rules"]
        ],
    }

print("MT_PROBE_RESULT " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def mt_extraction() -> MtProwideExtraction:
    return load_extraction()


def _finding_codes(findings: tuple[object, ...]) -> set[RuleFindingCode]:
    return {finding.code for finding in findings}  # type: ignore[attr-defined]


def _mt(field_id: str) -> FieldRef:
    return FieldRef(format=MessageFormat.MT, field_id=field_id)


def test_manifest_records_mt_source_scope_and_model_processing_policy() -> None:
    manifest = SourceManifest()
    source = manifest.get(SYNTHETIC_MT_SOURCE)
    assert source.source_type is RuleSourceType.SYNTHETIC_FIXTURE
    assert source.standards_release == "SR2025"
    assert source.applicable_message_categories == (5,)
    assert source.message_identifiers == ("MT541",)
    assert source.external_model_processing_allowed()

    ingested = manifest.ingest(SYNTHETIC_MT_SOURCE)
    reference = ingested.reference()
    assert reference.standards_release == "SR2025"
    assert reference.message_identifiers == ("MT541",)
    assert reference.source_allows_external_model_processing is True
    assert reference.provider_approved_for_source_classification is True

    real_source = SourceBundle(
        source_id="OPERATOR-MT",
        source_type=RuleSourceType.OPERATOR_SUPPLIED_MT_GUIDE,
        title="Operator supplied MT guide",
        version="1.0",
        source_location="operator-mt.md",
        standards_release="SR2025",
        applicable_message_categories=(5,),
        message_identifiers=("MT541",),
    )
    assert not real_source.external_model_processing_allowed()
    approved = real_source.model_copy(
        update={
            "source_allows_external_model_processing": True,
            "provider_approved_for_source_classification": True,
        }
    )
    assert approved.external_model_processing_allowed()


def test_non_synthetic_source_is_segmented_but_not_sent_to_a_model() -> None:
    text = normalise(
        "# Operator MT source\n\n"
        "This text is intentionally not approved for external model processing."
    )
    checksum = sha256_of(text)
    bundle = SourceBundle(
        source_id="OPERATOR-MT",
        source_type=RuleSourceType.OPERATOR_SUPPLIED_MT_GUIDE,
        title="Operator supplied MT guide",
        version="1.0",
        source_location="operator-mt.md",
        adapter=SourceAdapter.MARKDOWN,
        source_checksum=checksum,
        standards_release="SR2025",
        applicable_message_categories=(5,),
        message_identifiers=("MT541",),
        redistribution=Redistribution(),
    )
    source = IngestedSource(
        bundle=bundle,
        checksum=checksum,
        adapter=SourceAdapter.MARKDOWN,
        segments=tuple(segment_text(text, bundle.source_id, SourceAdapter.MARKDOWN)),
        page_count=0,
    )
    client = ScriptedCompletionClient()
    pipeline = RuleExtractionPipeline(
        client,
        StructureIndex(),
        models=ExtractionModels("extract-a", "extract-b", "refute"),
        cache=ExtractionCache(directory=Path("."), enabled=False),
    )

    run = asyncio.run(
        pipeline.run(source, format_=MessageFormat.MT, message_type="MT541")
    )

    assert client.calls == []
    assert run.metrics()["liveCalls"] == 0
    assert run.metrics()["tokensUsed"] == 0
    assert run.accepted == []
    assert _finding_codes(tuple(run.findings)) == {
        RuleFindingCode.RULE_EXTRACTION_PRIVACY_BLOCKED
    }


def test_mt_semantic_reference_resolves_structural_metadata_and_runtime_row(
    mt_extraction: MtProwideExtraction,
) -> None:
    resolved, findings = resolve_mt_semantic_reference(
        mt_extraction,
        MtSemanticReferenceRequest(
            message_type="MT541",
            standards_release="SR2025",
            sequence_path="SETDET",
            tag="22F",
            qualifier="SETR",
        ),
    )

    assert findings == ()
    assert resolved is not None
    assert resolved.canonical_id == "MT:SR2025:MT541:SETDET:22F:SETR"
    assert resolved.runtime_field_id == "MT541-E-22F-SETR"
    assert resolved.qualifier_status == "RESOLVED"


@pytest.mark.parametrize(
    ("reference_request", "expected"),
    [
        (
            MtSemanticReferenceRequest("MT000", "SETDET", "22F", qualifier="SETR"),
            RuleFindingCode.MT_RULE_MESSAGE_NOT_FOUND,
        ),
        (
            MtSemanticReferenceRequest(
                "MT541", "SETDET", "22F", standards_release="SR2024", qualifier="SETR"
            ),
            RuleFindingCode.MT_RULE_SRU_MISMATCH,
        ),
        (
            MtSemanticReferenceRequest("MT541", "NOSEQ", "22F", qualifier="SETR"),
            RuleFindingCode.MT_RULE_SEQUENCE_NOT_FOUND,
        ),
        (
            MtSemanticReferenceRequest("MT541", "SETDET", "99Z"),
            RuleFindingCode.MT_RULE_FIELD_NOT_FOUND,
        ),
        (
            MtSemanticReferenceRequest("MT541", "SETPRTY", "95P", option="R"),
            RuleFindingCode.MT_RULE_OPTION_NOT_RESOLVED,
        ),
        (
            MtSemanticReferenceRequest("MT541", "SETDET", "22F", qualifier="NOPE"),
            RuleFindingCode.MT_RULE_QUALIFIER_NOT_RESOLVED,
        ),
        (
            MtSemanticReferenceRequest("MT541", "GENL", "20C", qualifier="SEME", component=99),
            RuleFindingCode.MT_RULE_COMPONENT_NOT_FOUND,
        ),
        (
            MtSemanticReferenceRequest("MT541", "SETDET", "22F"),
            RuleFindingCode.MT_RULE_REFERENCE_AMBIGUOUS,
        ),
    ],
)
def test_mt_semantic_reference_failures_are_named(
    mt_extraction: MtProwideExtraction,
    reference_request: MtSemanticReferenceRequest,
    expected: RuleFindingCode,
) -> None:
    resolved, findings = resolve_mt_semantic_reference(mt_extraction, reference_request)
    assert resolved is None
    assert expected in _finding_codes(findings)


def test_generated_mt_readiness_reports_are_current() -> None:
    assert SEMANTIC_READINESS_DOCUMENT.read_text(encoding="utf-8") == (
        render_semantic_readiness()
    )
    assert SOURCE_READINESS_DOCUMENT.read_text(encoding="utf-8") == (
        render_source_readiness()
    )


def test_source_readiness_reports_real_mt_semantic_sources_absent() -> None:
    from app.studio.sources import SourceState, build_readiness

    report = build_readiness()
    mt_row = next(item for item in report.sources if item.id == "MT_SEMANTIC_RULE_SOURCES")
    assert mt_row.state is SourceState.ABSENT
    assert "0 authorised MT semantic source(s)" in mt_row.present
    assert "1 synthetic MT fixture(s)" in mt_row.present


def test_mt_rule_extraction_corpus_runs_offline() -> None:
    from app.rule_engine.evaluation.runner import run_evaluation

    report = run_evaluation(corpus_path=BACKEND / "config" / "rule_evaluation" / "mt-corpus.yaml")
    assert report.mode == "offline"
    assert report.corpus_size == 18
    assert report.passed, report.render()
    assert report.metrics["diff classification accuracy"] == "18/18"


def _install_reviewed_mt_pack(tmp_path: Path) -> Path:
    source = SourceManifest().ingest(SYNTHETIC_MT_SOURCE)
    segment = next(
        item for item in source.segments if item.heading == "Conditional receiving-agent policy"
    )
    index = StructureIndex()
    pack = RulePack(
        pack_id=f"MT:MT541:{RuleLayer.CLIENT_PROFILE.value}:{DEMO_PROFILE}:v1",
        format=MessageFormat.MT,
        message_type="MT541",
        layer=RuleLayer.CLIENT_PROFILE,
        profile_id=DEMO_PROFILE,
        pack_version="v1",
        title="Synthetic MT client-profile rule pack",
        engine_version=RULE_ENGINE_VERSION,
        dsl_version=DSL_VERSION,
        structure_compatibility=structure_compatibility_for(
            index, MessageFormat.MT, "MT541"
        ),
        review=RuleReview(
            status=RuleReviewStatus.REVIEWED,
            reviewed_by="Synthetic MT test reviewer",
            reviewed_at="SOURCE_CONTROLLED",
        ),
        sources=(source.reference(),),
        limitations=(
            "Synthetic test fixture. Not derived from SWIFT, MyStandards or any client.",
        ),
        rules=(
            Rule(
                rule_id="SYNTH-MT-CLIENT-REAG-FOR-TRAD",
                title="Trade settlements name the receiving agent",
                when=Predicate(
                    field=_mt("MT541-E-22F-SETR"),
                    operator=Operator.EQUALS,
                    value="TRAD",
                ),
                assert_=Predicate(
                    field=_mt("MT541-E-95P-REAG"),
                    operator=Operator.EXISTS,
                ),
                finding=RuleFindingText(
                    message="The synthetic client profile requires a receiving agent.",
                    suggestion="Provide the receiving-agent BIC for this synthetic profile.",
                ),
                evidence=(segment.evidence(source.bundle, excerpt_limit=400),),
                review=RuleReview(
                    status=RuleReviewStatus.REVIEWED,
                    reviewed_by="Synthetic MT test reviewer",
                    reviewed_at="SOURCE_CONTROLLED",
                ),
            ),
        ),
    )
    rules_dir = tmp_path / "rules"
    shutil.copytree(BACKEND / "config" / "rules", rules_dir)
    (rules_dir / pack.file_name()).write_text(pack_yaml(pack), encoding="utf-8")
    return rules_dir


def test_reviewed_synthetic_mt_pack_loads_only_for_its_profile(tmp_path: Path) -> None:
    rules_dir = _install_reviewed_mt_pack(tmp_path)
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "AI_PROVIDER": "disabled",
        "RULE_PACK_DIRECTORY": str(rules_dir),
        "DATABASE_URL": f"sqlite:///{tmp_path / 'probe.db'}",
        "PYTHONPATH": str(BACKEND),
    }
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", _MT_RUNTIME_PROBE],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    line = next(
        item
        for item in completed.stdout.splitlines()
        if item.startswith("MT_PROBE_RESULT ")
    )
    result = json.loads(line.removeprefix("MT_PROBE_RESULT "))

    assert result["brokenValid"] is False
    issue = result["issue"]
    assert issue["layer"] == "CLIENT_PROFILE"
    assert issue["ruleLayer"] == "Client rule"
    assert issue["rulePackId"] == f"MT:MT541:CLIENT_PROFILE:{DEMO_PROFILE}:v1"
    assert issue["sourceReference"].startswith(f"{SYNTHETIC_MT_SOURCE} ")
    assert issue["reviewStatus"] == "REVIEWED"
    assert issue["location"] == "MT541-E-95P-REAG"
    assert result["fixedValid"] is True
    assert result["plainValid"] is True
    assert "SYNTH-MT-CLIENT-REAG-FOR-TRAD" not in result["plainRuleIds"]
    assert "SYNTH-MT-CLIENT-REAG-FOR-TRAD" in result["intelligenceRules"]
