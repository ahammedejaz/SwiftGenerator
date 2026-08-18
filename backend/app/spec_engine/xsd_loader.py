"""Safe loading of untrusted XSD files and local schema bundles.

A schema is untrusted XML. Everything dangerous is refused up front, with a named
finding rather than a parser exception:

- any DOCTYPE (``XSD_DOCTYPE_FORBIDDEN``) — kills XXE and entity-expansion attacks in one
  move; no legitimate ISO 20022 schema carries one
- network schemaLocations (``XSD_REMOTE_FETCH_BLOCKED``) — compilation never fetches
- locations resolving outside the bundle root, symlinks included
  (``XSD_IMPORT_OUTSIDE_BUNDLE``)
- oversized files and oversized bundles

Includes merge into their including schema's namespace; imports load sibling namespaces.
Cycles are handled with a visited set. Missing dependencies name the namespace and the
location — never silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from app.spec_engine.diagnostics import (
    CompilationError,
    FindingCode,
    FindingLog,
)

XS = "http://www.w3.org/2001/XMLSchema"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_BUNDLE_FILES = 64


def _parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
    )


@dataclass
class LoadedSchema:
    """One parsed schema file plus what it asks for."""

    path: Path
    tree: etree._Element
    target_namespace: str
    includes: list[str] = field(default_factory=list)
    imports: list[tuple[str | None, str | None]] = field(default_factory=list)


@dataclass
class SchemaSet:
    """Every schema reachable from the entry file, keyed by target namespace.

    Includes are merged: a namespace maps to the list of schema elements contributing to
    it, entry file's contributions first.
    """

    entry: Path
    bundle_root: Path
    by_namespace: dict[str, list[LoadedSchema]] = field(default_factory=dict)

    def entry_namespace(self) -> str:
        for namespace, schemas in self.by_namespace.items():
            if any(item.path == self.entry for item in schemas):
                return namespace
        raise KeyError("entry schema namespace not loaded")


def _read_file(path: Path, log: FindingLog) -> bytes | None:
    try:
        size = path.stat().st_size
    except OSError:
        log.error(
            FindingCode.XSD_SOURCE_NOT_FOUND,
            f"{path.name} does not exist or cannot be read.",
            "Check the path passed to the compiler.",
            source=path.name,
        )
        return None
    if size > MAX_FILE_BYTES:
        log.error(
            FindingCode.XSD_SOURCE_TOO_LARGE,
            f"{path.name} is {size} bytes; the limit is {MAX_FILE_BYTES}.",
            "ISO 20022 message schemas are well under this limit; check the file.",
            source=path.name,
        )
        return None
    return path.read_bytes()


def _parse(path: Path, raw: bytes, log: FindingLog) -> etree._Element | None:
    # A DOCTYPE has no legitimate use in an ISO 20022 schema and is the vehicle for XXE
    # and entity-expansion attacks, so its presence is refused outright — cheaper and
    # stricter than trying to sandbox what it declares.
    head = raw[:4096].lstrip()
    if b"<!DOCTYPE" in raw:
        log.error(
            FindingCode.XSD_DOCTYPE_FORBIDDEN,
            f"{path.name} declares a DOCTYPE, which schema sources must not.",
            "Remove the DOCTYPE declaration; ISO 20022 schemas never need one.",
            source=path.name,
        )
        return None
    if not head.startswith((b"<?xml", b"<")):
        log.error(
            FindingCode.XSD_NOT_WELL_FORMED,
            f"{path.name} does not look like an XML document.",
            "Pass the .xsd file itself, not an archive or documentation file.",
            source=path.name,
        )
        return None
    try:
        root = etree.fromstring(raw, parser=_parser())
    except etree.XMLSyntaxError as error:
        log.error(
            FindingCode.XSD_NOT_WELL_FORMED,
            f"{path.name} is not well-formed XML: {error.msg}",
            "Fix the file or re-export it from its source.",
            source=path.name,
        )
        return None
    if root.tag != f"{{{XS}}}schema":
        log.error(
            FindingCode.XSD_UNSUPPORTED_CONSTRUCT,
            f"{path.name} is XML but its root is not xs:schema.",
            "Pass an XML Schema document.",
            source=path.name,
        )
        return None
    return root


def _resolve_location(
    location: str, relative_to: Path, bundle_root: Path, log: FindingLog
) -> Path | None:
    if location.startswith(("http://", "https://", "ftp://", "//")):
        log.error(
            FindingCode.XSD_REMOTE_FETCH_BLOCKED,
            f"{relative_to.name} asks for a remote schema: {location}",
            "Place every referenced schema inside the bundle directory and use a "
            "relative location.",
            source=relative_to.name,
        )
        return None
    candidate = (relative_to.parent / location).resolve()
    root = bundle_root.resolve()
    if not candidate.is_relative_to(root):
        log.error(
            FindingCode.XSD_IMPORT_OUTSIDE_BUNDLE,
            f"{relative_to.name} references {location}, which resolves outside the bundle.",
            "Keep every schema of a bundle under one directory.",
            source=relative_to.name,
        )
        return None
    # A symlink inside the bundle must not escape it either.
    if candidate.exists() and not candidate.resolve().is_relative_to(root):
        log.error(
            FindingCode.XSD_IMPORT_OUTSIDE_BUNDLE,
            f"{location} is a link that leaves the bundle directory.",
            "Copy the real file into the bundle instead of linking it.",
            source=relative_to.name,
        )
        return None
    return candidate


def _load_one(path: Path, log: FindingLog) -> LoadedSchema | None:
    raw = _read_file(path, log)
    if raw is None:
        return None
    root = _parse(path, raw, log)
    if root is None:
        return None
    target = root.get("targetNamespace") or ""
    includes = [
        item.get("schemaLocation") or ""
        for item in root.findall(f"{{{XS}}}include")
    ]
    imports = [
        (item.get("namespace"), item.get("schemaLocation"))
        for item in root.findall(f"{{{XS}}}import")
    ]
    return LoadedSchema(
        path=path, tree=root, target_namespace=target, includes=includes, imports=imports
    )


def load_schema_set(entry: Path, bundle_root: Path | None = None) -> SchemaSet:
    """Load the entry schema and everything it references, locally and safely.

    Raises :class:`CompilationError` carrying every finding when anything is refused —
    all problems are reported together rather than one per run.
    """
    log = FindingLog()
    entry = entry.resolve()
    root_dir = (bundle_root or entry.parent).resolve()
    schema_set = SchemaSet(entry=entry, bundle_root=root_dir)
    queue: list[Path] = [entry]
    visited: set[Path] = set()

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue  # cycles and diamonds are fine; each file loads once
        visited.add(current)
        if len(visited) > MAX_BUNDLE_FILES:
            log.error(
                FindingCode.XSD_BUNDLE_TOO_LARGE,
                f"The bundle references more than {MAX_BUNDLE_FILES} schema files.",
                "ISO 20022 bundles are far smaller; check for a reference loop.",
            )
            break
        loaded = _load_one(current, log)
        if loaded is None:
            continue
        schema_set.by_namespace.setdefault(loaded.target_namespace, []).append(loaded)
        for location in loaded.includes:
            resolved = _resolve_location(location, current, root_dir, log)
            if resolved is None:
                continue
            if not resolved.is_file():
                log.error(
                    FindingCode.XSD_IMPORT_NOT_FOUND,
                    f"{current.name} includes {location}, which is not in the bundle.",
                    "Add the missing schema file to the bundle directory.",
                    source=current.name,
                )
                continue
            queue.append(resolved)
        for namespace, import_location in loaded.imports:
            if import_location is None:
                # An import without a location is legal XSD; the namespace must then be
                # satisfied by another file already in the bundle. Checked after the walk.
                continue
            resolved = _resolve_location(import_location, current, root_dir, log)
            if resolved is None:
                continue
            if not resolved.is_file():
                log.error(
                    FindingCode.XSD_IMPORT_NOT_FOUND,
                    f"{current.name} imports {namespace or 'a namespace'} from "
                    f"{import_location}, which is not in the bundle.",
                    "Add the missing schema file to the bundle directory.",
                    source=current.name,
                )
                continue
            queue.append(resolved)

    # Imports without a schemaLocation must be satisfied by something loaded.
    for schemas in list(schema_set.by_namespace.values()):
        for schema in schemas:
            for namespace, unlocated in schema.imports:
                if unlocated is None and namespace not in schema_set.by_namespace:
                    log.error(
                        FindingCode.XSD_IMPORT_NOT_FOUND,
                        f"{schema.path.name} imports namespace {namespace} but no schema "
                        "in the bundle declares it.",
                        "Add the schema that declares that namespace to the bundle.",
                        source=schema.path.name,
                    )

    if log.blocked:
        raise CompilationError(log.findings)
    return schema_set
