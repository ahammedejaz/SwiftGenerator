from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_secure_local_bundle_is_verified_and_copied(tmp_path: Path) -> None:
    archive = tmp_path / "knowledge.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("MT/synthetic.txt", "Synthetic fixture")
    destination = tmp_path / "installed"
    environment = {
        **os.environ,
        "PYTHON": sys.executable,
        "KNOWLEDGE_BUNDLE_PATH": str(archive),
        "KNOWLEDGE_BUNDLE_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "KNOWLEDGE_BUNDLE_DESTINATION": str(destination),
    }

    result = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (destination / "MT/synthetic.txt").read_text() == "Synthetic fixture"


def test_archive_traversal_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "must not escape")
    destination = tmp_path / "extracted"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/extract-knowledge-bundle.py"),
            str(archive),
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not (tmp_path / "outside.txt").exists()


def test_http_bundle_url_is_rejected_before_network_access(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "KNOWLEDGE_BUNDLE_URL": "http://127.0.0.1/private.zip",
            "KNOWLEDGE_BUNDLE_PATH": "",
            "KNOWLEDGE_BUNDLE_SHA256": "0" * 64,
            "KNOWLEDGE_BUNDLE_DESTINATION": str(tmp_path / "installed"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "must use HTTPS" in result.stderr


def test_checksum_mismatch_is_rejected_without_installing(tmp_path: Path) -> None:
    archive = tmp_path / "knowledge.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("synthetic.txt", "Synthetic fixture")
    destination = tmp_path / "installed"

    result = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHON": sys.executable,
            "KNOWLEDGE_BUNDLE_PATH": str(archive),
            "KNOWLEDGE_BUNDLE_SHA256": "0" * 64,
            "KNOWLEDGE_BUNDLE_DESTINATION": str(destination),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "checksum mismatch" in result.stderr
    assert not destination.exists()


def test_missing_bundle_configuration_is_actionable(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env={
            **os.environ,
            "KNOWLEDGE_BUNDLE_URL": "",
            "KNOWLEDGE_BUNDLE_PATH": "",
            "KNOWLEDGE_BUNDLE_SHA256": "0" * 64,
            "KNOWLEDGE_BUNDLE_DESTINATION": str(tmp_path / "installed"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Set KNOWLEDGE_BUNDLE_URL or KNOWLEDGE_BUNDLE_PATH" in result.stderr


def test_https_download_resumes_and_reuses_verified_cache(tmp_path: Path) -> None:
    archive = tmp_path / "knowledge.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("MT/synthetic.txt", "Synthetic fixture")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$CURL_CALLS"
if [ "${CURL_MUST_NOT_RUN:-}" = "true" ]; then exit 99; fi
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--output" ]; then shift; output=$1; fi
  shift
done
cp "$FAKE_ARCHIVE" "$output"
""",
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)
    cache = tmp_path / "cache" / "bundle"
    calls = tmp_path / "curl-calls"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "PYTHON": sys.executable,
        "KNOWLEDGE_BUNDLE_URL": "https://artifacts.example/knowledge.zip",
        "KNOWLEDGE_BUNDLE_SHA256": checksum,
        "KNOWLEDGE_BUNDLE_CACHE": str(cache),
        "KNOWLEDGE_BUNDLE_DESTINATION": str(tmp_path / "installed"),
        "FAKE_ARCHIVE": str(archive),
        "CURL_CALLS": str(calls),
    }

    first = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    second = subprocess.run(
        [str(ROOT / "scripts/knowledge-fetch.sh")],
        cwd=ROOT,
        env={**environment, "CURL_MUST_NOT_RUN": "true"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "--continue-at -" in calls.read_text(encoding="utf-8")
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1
    assert (tmp_path / "installed/MT/synthetic.txt").read_text() == "Synthetic fixture"
