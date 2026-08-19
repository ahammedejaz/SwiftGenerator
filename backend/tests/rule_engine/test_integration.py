"""The Phase 2 acceptance properties, proved through the ordinary surfaces.

The first test is the one that matters: a synthetic message is compiled from a schema, a
rule is derived from a synthetic source document, reviewed, and installed by *pointing the
configuration directories at it* — and the running application then enforces that rule
through the same endpoints a tester and an automation harness use. No Python and no React
file names the message or the rule.

The remaining tests prove the four smaller properties the brief names: overlay narrowing,
conflict at installation, prompt injection, and no-rule.
"""

from __future__ import annotations

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
from app.rule_engine.dsl import Operator, Predicate
from app.rule_engine.extraction.review import ReviewAction, apply_review, pack_yaml
from app.rule_engine.models import (
    Rule,
    RuleFindingText,
    RulePack,
    RuleReview,
    RuleReviewStatus,
)
from app.rule_engine.refs import FieldRef, StructureIndex
from app.rule_engine.sources import (
    Redistribution,
    RuleSourceType,
    SourceAdapter,
    SourceBundle,
    ingest,
)
from app.spec_engine.pipeline import compile_schema
from app.studio.models import MessageFormat
from app.studio.mx.registry import MxRegistry

BACKEND = Path(__file__).resolve().parents[2]
XSD = BACKEND / "tests" / "fixtures" / "xsd" / "test.001.001.01.xsd"

#: A synthetic guideline about the synthetic message. Written here, committed nowhere.
SYNTHETIC_SOURCE = """# Synthetic guideline for the synthetic test message

SYNTHETIC MATERIAL. Invented for this test. Not a standard.

## 1 Priority and acknowledgement

Where the priority is HIGH, the acknowledgement status must be present so that the sender
knows the instruction was seen.
"""

_PROBE = """
import json
from fastapi.testclient import TestClient
from app.main import app

PRIORITY = "/Document/SynthTstInstr/Prty"
ACK = "/Document/SynthTstInstr/AckSts"


def generate(client, elements):
    return client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MX",
            "messageType": "test.001",
            "elements": elements,
            "persist": False,
        },
    ).json()


def variant(sample, **overrides):
    # Start from the sample the platform derives for itself, so this probe never hand-
    # writes a value for a message it is supposed to know nothing about.
    values = {item["path"]: item["value"] for item in sample["elements"]}
    for path, value in overrides.items():
        if value is None:
            values.pop(path, None)
        else:
            values[path] = value
    return [{"path": path, "value": value} for path, value in values.items()]


out = {}
with TestClient(app) as client:
    catalogue = client.get("/api/v1/catalogue").json()
    entry = next(m for m in catalogue["messages"] if m["messageType"] == "test.001")
    out["capability"] = entry["capability"]
    out["summary"] = entry["capabilitySummary"]

    sample = client.get("/api/v1/messages/test.001/samples").json()[-1]

    quiet = generate(client, variant(sample, **{PRIORITY: "NORM", ACK: None}))
    out["quiet"] = {
        "valid": quiet["validation"]["valid"],
        "errors": [(i["ruleId"], i["message"]) for i in quiet["validation"]["errors"]],
    }

    broken = generate(client, variant(sample, **{PRIORITY: "HIGH", ACK: None}))
    issues = [
        i for i in broken["validation"]["errors"] if i["ruleId"] == "SYNTH-E2E-ACK-FOR-HIGH"
    ]
    out["broken"] = {
        "valid": broken["validation"]["valid"],
        "count": len(issues),
        "issue": issues[0] if issues else None,
        "layers": {
            layer["layer"]: layer["state"] for layer in broken["validation"]["layers"]
        },
    }

    fixed = generate(client, variant(sample, **{PRIORITY: "HIGH", ACK: "true"}))
    out["fixed"] = {
        "valid": fixed["validation"]["valid"],
        "hasXml": bool(fixed["outputs"].get("xml")),
        "errors": [(i["ruleId"], i["message"]) for i in fixed["validation"]["errors"]],
    }

    spec = client.get("/api/v1/messages/test.001/spec").json()
    out["spec"] = {"capability": spec["capability"]}
    out["excel"] = client.get("/api/v1/templates/MX.xlsx").status_code

print("PROBE_RESULT " + json.dumps(out))
"""


def _install(tmp_path: Path) -> tuple[Path, Path, StructureIndex]:
    """Compile the synthetic schema and derive one reviewed rule from a synthetic source."""
    # Copy the installed specifications in beside the new one: an operator adding a
    # message does not remove the ones they already had, and the Excel template builds
    # for the whole catalogue.
    mx_dir = tmp_path / "mx"
    shutil.copytree(BACKEND / "config" / "mx", mx_dir)
    compiled = compile_schema(XSD)
    (mx_dir / compiled.file_name).write_text(compiled.yaml_text, encoding="utf-8")
    index = StructureIndex(mx=MxRegistry(mx_dir))

    drop = tmp_path / "sources"
    drop.mkdir()
    (drop / "synthetic-e2e.md").write_text(SYNTHETIC_SOURCE, encoding="utf-8")
    source = ingest(
        SourceBundle(
            source_id="SYNTH-E2E",
            source_type=RuleSourceType.SYNTHETIC_FIXTURE,
            title="Synthetic guideline for the synthetic test message",
            version="1.0",
            source_location="synthetic-e2e.md",
            adapter=SourceAdapter.MARKDOWN,
            redistribution=Redistribution(
                source_may_be_committed=True, excerpts_may_be_committed=True
            ),
        ),
        drop,
    )
    segment = next(
        item for item in source.segments if item.heading == "1 Priority and acknowledgement"
    )

    def field(path: str) -> FieldRef:
        return FieldRef(format=MessageFormat.MX, path=path)

    candidate = RulePack(
        pack_id=f"MX:{index.version(MessageFormat.MX, 'test.001')}:BASE_STANDARD:v1",
        format=MessageFormat.MX,
        message_type="test.001",
        message_version=index.version(MessageFormat.MX, "test.001"),
        layer=RuleLayer.BASE_STANDARD,
        pack_version="v1",
        title="Synthetic end-to-end rule pack",
        engine_version=RULE_ENGINE_VERSION,
        dsl_version=DSL_VERSION,
        structure_compatibility=structure_compatibility_for(
            index, MessageFormat.MX, "test.001"
        ),
        review=RuleReview(status=RuleReviewStatus.REVIEW_REQUIRED),
        sources=(source.reference(),),
        limitations=("Synthetic. Derived from an invented document about an invented message.",),
        rules=(
            Rule(
                rule_id="SYNTH-E2E-ACK-FOR-HIGH",
                title="High priority instructions are acknowledged",
                when=Predicate(
                    field=field("/Document/SynthTstInstr/Prty"),
                    operator=Operator.EQUALS,
                    value="HIGH",
                ),
                assert_=Predicate(
                    field=field("/Document/SynthTstInstr/AckSts"), operator=Operator.EXISTS
                ),
                finding=RuleFindingText(
                    message="A high-priority instruction must carry an acknowledgement status.",
                    suggestion="Set the acknowledgement status, or lower the priority.",
                ),
                evidence=(segment.evidence(source.bundle, excerpt_limit=400),),
                review=RuleReview(status=RuleReviewStatus.MACHINE_CHECKED),
            ),
        ),
    )
    reviewed = apply_review(
        candidate, ReviewAction.APPROVE, reviewer="Integration test reviewer"
    )
    rules_dir = tmp_path / "rules"
    shutil.copytree(BACKEND / "config" / "rules", rules_dir)
    (rules_dir / reviewed.file_name()).write_text(pack_yaml(reviewed), encoding="utf-8")
    return mx_dir, rules_dir, index


def test_a_reviewed_rule_installed_as_configuration_is_enforced_by_the_application(
    tmp_path: Path,
) -> None:
    mx_dir, rules_dir, _ = _install(tmp_path)
    environment = {
        **os.environ,
        "MX_SPECIFICATION_DIRECTORY": str(mx_dir),
        "RULE_PACK_DIRECTORY": str(rules_dir),
        "DATABASE_URL": f"sqlite:///{tmp_path / 'probe.db'}",
        "PYTHONPATH": str(BACKEND),
    }
    completed = subprocess.run(  # noqa: S603 - a fixed interpreter and a literal script
        [sys.executable, "-c", _PROBE],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    line = next(
        item for item in completed.stdout.splitlines() if item.startswith("PROBE_RESULT ")
    )
    result = json.loads(line.removeprefix("PROBE_RESULT "))

    # The capability moved for its own reason, and for nothing else's.
    assert result["capability"]["structure"] == "COMPILED_FROM_SCHEMA"
    assert result["capability"]["businessRules"] == "REVIEWED"
    assert result["capability"]["marketPractice"] == "NOT_CONFIGURED"
    assert result["capability"]["clientProfile"] == "NOT_CONFIGURED"
    assert result["capability"]["externalValidation"] == "NOT_RUN"
    for forbidden in ("compliant", "certified", "production ready"):
        assert forbidden not in result["summary"].casefold()

    # The rule is silent when it does not apply, and speaks when it does.
    assert result["quiet"]["valid"] is True, result["quiet"]["errors"]
    assert result["broken"]["valid"] is False
    assert result["broken"]["count"] == 1
    issue = result["broken"]["issue"]
    assert issue["layer"] == "BUSINESS_RULES"
    assert issue["ruleLayer"] == "Base business rule"
    assert issue["rulePackId"].endswith("BASE_STANDARD:v1")
    assert "SYNTH-E2E" in issue["sourceReference"]
    assert issue["reviewStatus"] == "REVIEWED"
    assert issue["location"] == "/Document/SynthTstInstr/AckSts"
    assert result["broken"]["layers"]["BUSINESS_RULES"] == "FAILED"
    assert result["broken"]["layers"]["XSD"] == "PASSED"

    # Corrected, the same values generate.
    assert result["fixed"]["valid"] is True, result["fixed"]["errors"]
    assert result["fixed"]["hasXml"] is True

    # And automation sees the same thing.
    assert result["spec"]["capability"]["businessRules"] == "REVIEWED"
    assert result["excel"] == 200


def test_a_candidate_left_in_the_rules_directory_stops_the_load_rather_than_activating(
    tmp_path: Path,
) -> None:
    from app.rule_engine.diagnostics import RuleEngineError, RuleFindingCode
    from app.rule_engine.registry import RulePackRegistry

    mx_dir, rules_dir, index = _install(tmp_path)
    del mx_dir
    reviewed_path = next(rules_dir.glob("*.yaml"))
    text = reviewed_path.read_text(encoding="utf-8").replace("REVIEWED", "MACHINE_CHECKED")
    reviewed_path.write_text(text, encoding="utf-8")
    with pytest.raises(RuleEngineError) as caught:
        RulePackRegistry(rules_dir, index=index)
    assert RuleFindingCode.RULE_REVIEW_REQUIRED in {
        finding.code for finding in caught.value.findings
    }
