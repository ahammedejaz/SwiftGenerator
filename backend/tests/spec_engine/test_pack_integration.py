"""The Phase 1 acceptance property: a compiled pack drives the whole platform.

A synthetic message is compiled from XSD and installed by *pointing the configuration
directories at it* — the application is started in a subprocess with
``MX_SPECIFICATION_DIRECTORY`` and ``MX_OFFICIAL_XSD_DIRECTORY`` overridden, exactly the
drop-in mechanism an operator uses. The assertions then walk the ordinary surfaces:
catalogue, spec, samples, generation (validated OFFICIAL against the source schema),
Excel template, Message Intelligence and import round trip.

No Python or React file names the new message. That is the point.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.spec_engine.pipeline import compile_schema

BACKEND = Path(__file__).resolve().parents[2]
FIXTURE = BACKEND / "tests" / "fixtures" / "xsd" / "test.001.001.01.xsd"

_PROBE = """
import json
from fastapi.testclient import TestClient
from app.main import app

out = {}
with TestClient(app) as client:
    catalogue = client.get("/api/v1/catalogue").json()
    entry = next(m for m in catalogue["messages"] if m["messageType"] == "test.001")
    out["catalogue"] = {
        "generatable": entry["generatable"],
        "structure": entry["capability"]["structure"],
        "businessRules": entry["capability"]["businessRules"],
    }

    spec = client.get("/api/v1/messages/test.001/spec").json()
    out["spec"] = {
        "fieldCount": len(spec["fields"]),
        "hasChoice": any(f["choiceGroup"] for f in spec["fields"]),
    }

    samples = client.get("/api/v1/messages/test.001/samples").json()
    sample = samples[-1]  # the fullest variant the pack supports
    generated = client.post(
        "/api/v1/messages/generate",
        json={
            "format": "MX",
            "messageType": "test.001",
            "elements": sample["elements"],
            "persist": False,
        },
    ).json()
    xsd_layer = next(
        layer for layer in generated["validation"]["layers"] if layer["layer"] == "XSD"
    )
    out["generate"] = {
        "valid": generated["validation"]["valid"],
        "xsdState": xsd_layer["state"],
        "schemaSource": generated["outputs"]["canonicalJson"]["schemaSource"],
        "hasXml": bool(generated["outputs"].get("xml")),
    }

    excel = client.get("/api/v1/templates/MX.xlsx")
    out["excel"] = {"ok": excel.status_code == 200, "bytes": len(excel.content)}

    hits = client.get(
        "/api/v1/intelligence/search", params={"q": "SynthTstInstr"}
    ).json()
    out["intelligence"] = {"hits": len(hits["results"])}

    imported = client.post(
        "/api/v1/messages/import",
        json={"text": generated["outputs"]["xml"]},
    ).json()
    out["import"] = {
        "messageType": imported["messageType"],
        "problems": len(imported.get("problems", [])),
    }

print(json.dumps(out))
"""


def test_a_compiled_pack_drives_catalogue_form_excel_api_and_import(
    tmp_path: Path,
) -> None:
    pack = compile_schema(FIXTURE)

    mx_dir = tmp_path / "mx"
    mx_dir.mkdir()
    for existing in (BACKEND / "config" / "mx").glob("*.yaml"):
        shutil.copy(existing, mx_dir / existing.name)
    (mx_dir / pack.file_name).write_text(pack.yaml_text, encoding="utf-8")

    xsd_dir = tmp_path / "xsd"
    xsd_dir.mkdir()
    shutil.copy(FIXTURE, xsd_dir / f"{pack.version}.xsd")

    env = {
        **os.environ,
        "MX_SPECIFICATION_DIRECTORY": str(mx_dir),
        "MX_OFFICIAL_XSD_DIRECTORY": str(xsd_dir),
        "DATABASE_URL": "sqlite://",
        "APP_ENV": "development",
        "AI_PROVIDER": "disabled",
        "PYTHONPATH": str(BACKEND),
    }
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        cwd=BACKEND,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["catalogue"]["generatable"] is True
    # Structure is compiled; nothing else is upgraded by compilation.
    assert result["catalogue"]["structure"] == "COMPILED_FROM_SCHEMA"
    assert result["catalogue"]["businessRules"] == "NOT_CONFIGURED"

    assert result["spec"]["fieldCount"] >= 8
    assert result["spec"]["hasChoice"] is True

    assert result["generate"]["valid"] is True
    assert result["generate"]["xsdState"] == "PASSED"
    # The official-schema drop point picked up the source schema, so the generated
    # document was validated against the actual source XSD inside the application.
    assert result["generate"]["schemaSource"] == "OFFICIAL"
    assert result["generate"]["hasXml"] is True

    assert result["excel"]["ok"] is True
    assert result["intelligence"]["hits"] >= 1

    assert result["import"]["messageType"] == "test.001"
    assert result["import"]["problems"] == 0
