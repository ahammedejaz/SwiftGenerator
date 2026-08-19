from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.spec_engine.mt_prowide.models import (
    MtGlobalFieldEvidence,
    MtProwideParseResult,
)
from app.spec_engine.mt_prowide.source import REPO_ROOT, DownloadedArtifacts

_PROBE_SOURCE = REPO_ROOT / "tools" / "mt-prowide-extractor" / "MtProwideProbe.java"


def field_definitions(
    artifacts: DownloadedArtifacts,
    tags: list[str],
) -> list[MtGlobalFieldEvidence]:
    if not tags:
        return []
    class_dir = _compile_probe(artifacts)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "field-definitions.json"
        _run_probe(
            artifacts,
            class_dir,
            ["field-defs", str(out), *tags],
        )
        raw = json.loads(out.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Prowide field-defs probe returned a non-list payload")
    return [MtGlobalFieldEvidence.model_validate(item) for item in raw]


def parse_fin(
    artifacts: DownloadedArtifacts,
    message_type: str,
    fin: str,
) -> MtProwideParseResult:
    class_dir = _compile_probe(artifacts)
    with tempfile.TemporaryDirectory() as tmp:
        input_path = Path(tmp) / "message.fin"
        output_path = Path(tmp) / "parsed.json"
        input_path.write_text(fin, encoding="utf-8")
        _run_probe(
            artifacts,
            class_dir,
            ["parse", message_type, str(input_path), str(output_path)],
        )
        raw = json.loads(output_path.read_text(encoding="utf-8"))
    return MtProwideParseResult.model_validate(raw)


def _compile_probe(artifacts: DownloadedArtifacts) -> Path:
    if not _PROBE_SOURCE.exists():
        raise RuntimeError(f"Prowide Java probe source is missing: {_PROBE_SOURCE}")
    class_dir = artifacts.cache_dir / "classes"
    target = class_dir / "MtProwideProbe.class"
    if target.exists() and target.stat().st_mtime >= _PROBE_SOURCE.stat().st_mtime:
        return class_dir
    class_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "javac",
        "-Xlint:deprecation",
        "-cp",
        _classpath(artifacts.classpath),
        "-d",
        str(class_dir),
        str(_PROBE_SOURCE),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(_command_error("javac", result))
    return class_dir


def _run_probe(
    artifacts: DownloadedArtifacts,
    class_dir: Path,
    args: list[str],
) -> None:
    command = [
        "java",
        "-cp",
        _classpath((class_dir, *artifacts.classpath)),
        "MtProwideProbe",
        *args,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(_command_error("java MtProwideProbe", result))


def _classpath(paths: tuple[Path, ...]) -> str:
    return os.pathsep.join(str(path) for path in paths)


def _command_error(name: str, result: subprocess.CompletedProcess[str]) -> str:
    stderr = _clean_output(result.stderr)
    stdout = _clean_output(result.stdout)
    detail = stderr or stdout or "no output"
    return f"{name} failed with exit code {result.returncode}: {detail}"


def _clean_output(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def json_object(value: str) -> dict[str, Any]:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        raise RuntimeError("Expected a JSON object")
    return raw
