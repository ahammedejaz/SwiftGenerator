from __future__ import annotations

import hashlib
import shutil
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.spec_engine.mt_prowide.models import ArtifactRole, ProwideArtifact, ProwideSourceLock

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_LOCK = BACKEND_ROOT / "config" / "mt_prowide_sru2025_10_3_18.lock.yaml"
DEFAULT_CACHE = REPO_ROOT / "build" / "mt-prowide-cache"
DEFAULT_FIXTURE = (
    BACKEND_ROOT
    / "tests"
    / "fixtures"
    / "mt_prowide"
    / "all-categories-sru2025-10.3.18.json"
)


@dataclass(frozen=True)
class DownloadedArtifacts:
    lock: ProwideSourceLock
    cache_dir: Path
    core_jar: Path
    source_jar: Path
    classpath: tuple[Path, ...]


def load_lock(path: Path = DEFAULT_LOCK) -> ProwideSourceLock:
    with path.open(encoding="utf-8") as handle:
        return ProwideSourceLock.model_validate(yaml.safe_load(handle))


def ensure_artifacts(
    lock_path: Path = DEFAULT_LOCK,
    cache_dir: Path = DEFAULT_CACHE,
) -> DownloadedArtifacts:
    lock = load_lock(lock_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    core_jar: Path | None = None
    source_jar: Path | None = None
    for artifact in lock.artifacts:
        path = cache_dir / artifact.file_name
        _ensure_artifact(artifact, path)
        paths.append(path)
        if artifact.role is ArtifactRole.CORE_JAR:
            core_jar = path
        elif artifact.role is ArtifactRole.SOURCE_JAR:
            source_jar = path
    if core_jar is None or source_jar is None:
        raise RuntimeError("Prowide source lock must include core_jar and source_jar artifacts")
    classpath = tuple(
        path
        for artifact, path in zip(lock.artifacts, paths, strict=True)
        if artifact.role is not ArtifactRole.SOURCE_JAR
    )
    return DownloadedArtifacts(
        lock=lock,
        cache_dir=cache_dir,
        core_jar=core_jar,
        source_jar=source_jar,
        classpath=classpath,
    )


def _ensure_artifact(artifact: ProwideArtifact, path: Path) -> None:
    if path.exists() and _sha256(path) == artifact.sha256:
        return
    if path.exists():
        path.unlink()
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    request = urllib.request.Request(
        artifact.url,
        headers={"User-Agent": "SwiftGenerator-mt-prowide-source/1"},
    )
    with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
        with tmp.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    actual = _sha256(tmp)
    if actual != artifact.sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Checksum mismatch for {artifact.coordinate}: expected {artifact.sha256}, got {actual}"
        )
    tmp.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
