"""The specification engine CLI — the developer front door.

    .venv/bin/python -m app.spec_engine compile SOURCE.xsd [--out DIR] [--root NAME]
    .venv/bin/python -m app.spec_engine validate PACK.yaml --source SOURCE.xsd
    .venv/bin/python -m app.spec_engine inspect SOURCE.xsd
    .venv/bin/python -m app.spec_engine diff BEFORE.yaml AFTER.yaml
    .venv/bin/python -m app.spec_engine mt-prowide-reports --check
    .venv/bin/python -m app.spec_engine mt-prowide-verify

Compilation is offline by design: the running application never compiles a schema and
never mutates its own registry. A compiled pack becomes active the way any configuration
does — reviewed, committed, loaded at startup.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from app.spec_engine.diagnostics import CompilationError
from app.spec_engine.gates import validate_pack
from app.spec_engine.mt_prowide.extractor import (
    canonical_json,
    cross_engine_mt541,
    extract_all_categories,
    verify_fixture_against_source,
    write_extraction,
)
from app.spec_engine.mt_prowide.reports import check_reports, write_reports
from app.spec_engine.mt_prowide.source import DEFAULT_CACHE, DEFAULT_FIXTURE, DEFAULT_LOCK
from app.spec_engine.pipeline import compile_schema
from app.spec_engine.source import (
    acquire_manifest_sources,
    discover_message_sets,
    discover_messages,
    fetch_message_set_bundle,
    fetch_source,
    index_message_set_bundle,
    load_manifest,
    manifest_yaml,
    render_batch_report,
    render_bundle_index,
    run_scaleout,
)
from app.spec_engine.structdiff import diff_packs
from app.studio.mx.models import MxMessageSpec


def _cmd_compile(args: argparse.Namespace) -> int:
    source = Path(args.source)
    try:
        pack = compile_schema(
            source,
            bundle_root=Path(args.bundle) if args.bundle else None,
            source_type=args.source_type,
            root_name=args.root,
        )
    except CompilationError as error:
        for finding in error.findings:
            print(finding.render(), file=sys.stderr)
        return 1
    for finding in pack.findings:
        print(finding.render(), file=sys.stderr)

    out_dir = Path(args.out) if args.out else source.parent
    target = out_dir / pack.file_name
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if pack.source_checksum not in existing and not args.force:
            print(
                f"{target} already exists and was compiled from a different source "
                f"(its recorded checksum differs). Pass --force to overwrite.",
                file=sys.stderr,
            )
            return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pack.yaml_text, encoding="utf-8")
    print(f"wrote {target} ({pack.message_type}, {pack.version})")
    if args.validate:
        result = validate_pack(pack.yaml_text, pack.version, source)
        print(result.render())
        return 0 if result.passed else 1
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    pack_path = Path(args.pack)
    spec = MxMessageSpec.model_validate(
        yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    )
    result = validate_pack(
        pack_path.read_text(encoding="utf-8"), spec.version, Path(args.source)
    )
    print(result.render())
    return 0 if result.passed else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    source = Path(args.source)
    try:
        pack = compile_schema(source, root_name=args.root)
    except CompilationError as error:
        for finding in error.findings:
            print(finding.render(), file=sys.stderr)
        return 1
    spec = pack.spec
    leaves = 0

    def count(elements) -> int:  # type: ignore[no-untyped-def]
        total = 0
        for element in elements:
            total += 1 if element.is_leaf else count(element.children)
        return total

    leaves = count(spec.structure)
    print(f"message:   {spec.message_type} ({spec.version})")
    print(f"namespace: {spec.namespace}")
    print(f"root:      {spec.document_element}/{spec.message_root}")
    print(f"leaves:    {leaves}")
    print(f"checksum:  {pack.source_checksum}")
    for finding in pack.findings:
        print(finding.render())
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    before = MxMessageSpec.model_validate(
        yaml.safe_load(Path(args.before).read_text(encoding="utf-8"))
    )
    after = MxMessageSpec.model_validate(
        yaml.safe_load(Path(args.after).read_text(encoding="utf-8"))
    )
    result = diff_packs(before, after)
    print(result.render())
    return 0 if result.identical else 2


def _cmd_source_discover(args: argparse.Namespace) -> int:
    manifest = discover_messages(args.logical)
    text = manifest_yaml(manifest)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(
            f"wrote {target} ({len(manifest.messages)} message definitions, "
            f"{len(manifest.unresolved)} unresolved)"
        )
    else:
        print(text)
    return 0 if manifest.messages else 2


def _cmd_source_fetch(args: argparse.Namespace) -> int:
    try:
        result = fetch_source(
            args.url,
            Path(args.out),
            expected_message_definition=args.expected_message_definition,
            expected_checksum=args.expected_checksum,
        )
    except Exception as error:  # noqa: BLE001 - CLI surface is a concise acquisition error.
        print(f"source fetch failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote {result.path}")
    print(f"final-url: {result.final_url}")
    print(f"checksum: {result.checksum}")
    print(f"content-type: {result.content_type}")
    print(f"size: {result.size}")
    if result.redirects:
        print("redirects:")
        for item in result.redirects:
            print(f"- {item}")
    return 0


def _cmd_message_set_discover(args: argparse.Namespace) -> int:
    try:
        message_sets = discover_message_sets(args.family)
    except Exception as error:  # noqa: BLE001 - CLI surface is a concise acquisition error.
        print(f"message-set discovery failed: {error}", file=sys.stderr)
        return 1
    if not message_sets:
        print("no message-set download links discovered")
        return 2
    rows = [
        item.model_dump(by_alias=True, mode="json", exclude_none=True) for item in message_sets
    ]
    print(
        yaml.safe_dump(
            rows,
            sort_keys=False,
            allow_unicode=False,
        ).strip()
    )
    return 0


def _cmd_message_set_fetch(args: argparse.Namespace) -> int:
    try:
        result = fetch_message_set_bundle(
            args.url,
            Path(args.out),
            message_set_name=args.message_set_name or args.family or "ISO message set",
        )
    except CompilationError as error:
        for finding in error.findings:
            print(finding.render(), file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - CLI surface is a concise acquisition error.
        print(f"message-set fetch failed: {error}", file=sys.stderr)
        return 1
    print(f"wrote {result.path}")
    print(f"final-url: {result.final_url}")
    print(f"checksum: {result.checksum}")
    print(f"content-type: {result.content_type}")
    print(f"size: {result.size}")
    if result.redirects:
        print("redirects:")
        for item in result.redirects:
            print(f"- {item}")
    print(render_bundle_index(result.index))
    return 0


def _cmd_message_set_inspect(args: argparse.Namespace) -> int:
    try:
        index = index_message_set_bundle(
            Path(args.bundle),
            destination=Path(args.sources),
            message_set_name=args.message_set_name or args.family or "ISO message set",
        )
    except CompilationError as error:
        for finding in error.findings:
            print(finding.render(), file=sys.stderr)
        return 1
    print(render_bundle_index(index))
    return 0


def _cmd_source_acquire(args: argparse.Namespace) -> int:
    manifest = acquire_manifest_sources(
        Path(args.manifest),
        source_dir=Path(args.sources),
        out_manifest=Path(args.out) if args.out else None,
        allow_individual_fallback=not args.bundle_only,
    )
    acquired = sum(1 for item in manifest.messages if item.source_checksum)
    print(
        f"acquired {acquired}/{len(manifest.messages)} message definition source(s), "
        f"{len(manifest.unresolved)} unresolved"
    )
    if args.out:
        print(f"wrote {args.out}")
    if manifest.unresolved:
        print("unresolved:")
        for item in manifest.unresolved:
            print(f"- {item}")
    return 0 if acquired else 2


def _cmd_source_inspect(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest))
    print(f"manifest: {args.manifest}")
    print(f"retrieved: {manifest.retrieved_at}")
    print(f"source: {manifest.source_url}")
    print(f"messages: {len(manifest.messages)}")
    if manifest.unresolved:
        print("unresolved:")
        for unresolved in manifest.unresolved:
            print(f"- {unresolved}")
    if manifest.logical_messages:
        print("logical definitions:")
        for logical in manifest.logical_messages:
            current = ", ".join(logical.current_definitions) or "-"
            archived = ", ".join(logical.archived_definitions) or "-"
            print(f"- {logical.logical_message}: current=[{current}] archived=[{archived}]")
    if manifest.message_sets:
        print("message sets:")
        for message_set in manifest.message_sets:
            print(
                f"- {message_set.message_set_name}: "
                f"{message_set.download_url or message_set.bundle_location or 'unresolved'}"
            )
    for entry in manifest.messages:
        print(
            f"- {entry.logical_message} -> {entry.message_definition} "
            f"({entry.catalogue_state.value}, {entry.redistribution_status.value})"
        )
    return 0


def _cmd_scaleout(args: argparse.Namespace) -> int:
    result = run_scaleout(
        Path(args.manifest),
        source_dir=Path(args.sources),
        candidates_dir=Path(args.out),
    )
    report = render_batch_report(result)
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report, encoding="utf-8")
        print(f"wrote {target}")
    print(report)
    return 0 if result.failed == 0 else 1


def _cmd_mt_prowide_extract(args: argparse.Namespace) -> int:
    extraction = extract_all_categories(
        lock_path=Path(args.lock),
        cache_dir=Path(args.cache),
    )
    if args.out:
        write_extraction(extraction, Path(args.out))
        print(
            f"wrote {args.out} "
            f"({len(extraction.messages)} Prowide MT source model classes)"
        )
    else:
        print(canonical_json(extraction), end="")
    return 0


def _cmd_mt_prowide_reports(args: argparse.Namespace) -> int:
    fixture = Path(args.fixture)
    if args.write:
        write_reports(fixture)
        print("wrote MT Prowide generated reports")
        return 0
    stale = check_reports(fixture)
    if stale:
        print("MT Prowide generated reports are stale:")
        for path in stale:
            print(f"- {path}")
        return 1
    print("MT Prowide generated reports are current")
    return 0


def _cmd_mt_prowide_verify(args: argparse.Namespace) -> int:
    fixture_ok, fresh = verify_fixture_against_source(
        fixture=Path(args.fixture),
        lock_path=Path(args.lock),
        cache_dir=Path(args.cache),
    )
    if args.out:
        write_extraction(fresh, Path(args.out))
        print(f"wrote fresh extraction to {args.out}")
    cross = cross_engine_mt541(lock_path=Path(args.lock), cache_dir=Path(args.cache))
    print(
        f"source extraction: {'PASS' if fixture_ok else 'FAIL'} "
        f"({len(fresh.messages)} Prowide MT source model classes)"
    )
    print(
        f"MT541 Prowide parse proof: {'PASS' if cross.tag_stream_identical else 'FAIL'} "
        f"({cross.python_tag_count} Python tags, {cross.prowide_tag_count} Prowide tags)"
    )
    print(
        "Python import issues: "
        f"{cross.python_import_errors} error(s), "
        f"{cross.python_import_warnings} warning(s)"
    )
    if not fixture_ok:
        print("Committed MT Prowide fixture differs from the pinned source extraction.")
        return 1
    if (
        not cross.tag_stream_identical
        or cross.python_import_errors
        or cross.python_tag_count != cross.prowide_tag_count
    ):
        print("MT541 cross-engine parse proof failed.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.spec_engine", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    compile_cmd = commands.add_parser("compile", help="compile an XSD into a pack")
    compile_cmd.add_argument("source", help="the message .xsd (entry file of its bundle)")
    compile_cmd.add_argument("--bundle", help="bundle root directory (default: the source's)")
    compile_cmd.add_argument("--out", help="directory to write the pack into")
    compile_cmd.add_argument("--root", help="global element to treat as the document")
    compile_cmd.add_argument(
        "--source-type",
        default="OPERATOR_SUPPLIED_XSD",
        help="provenance label recorded in the pack. Declaring a source official is an "
        "explicit statement — pass OFFICIAL_ISO_20022_XSD only for the genuine artifact "
        "obtained under your licence; the default records no such claim.",
    )
    compile_cmd.add_argument(
        "--force", action="store_true", help="overwrite a pack from a different source"
    )
    compile_cmd.add_argument(
        "--validate", action="store_true", help="run the pack gates after compiling"
    )
    compile_cmd.set_defaults(handler=_cmd_compile)

    validate_cmd = commands.add_parser("validate", help="run the gates over a pack")
    validate_cmd.add_argument("pack", help="the pack .yaml")
    validate_cmd.add_argument("--source", required=True, help="the source .xsd to prove against")
    validate_cmd.set_defaults(handler=_cmd_validate)

    inspect_cmd = commands.add_parser("inspect", help="summarise what a schema compiles to")
    inspect_cmd.add_argument("source")
    inspect_cmd.add_argument("--root")
    inspect_cmd.set_defaults(handler=_cmd_inspect)

    diff_cmd = commands.add_parser("diff", help="structural diff of two packs")
    diff_cmd.add_argument("before")
    diff_cmd.add_argument("after")
    diff_cmd.set_defaults(handler=_cmd_diff)

    source_discover_cmd = commands.add_parser(
        "source-discover", help="resolve logical message IDs from the official ISO catalogue"
    )
    source_discover_cmd.add_argument("logical", nargs="+", help="logical IDs such as pacs.008")
    source_discover_cmd.add_argument("--out", help="write a metadata-only source manifest")
    source_discover_cmd.set_defaults(handler=_cmd_source_discover)

    source_fetch_cmd = commands.add_parser(
        "source-fetch", help="fetch one iso20022.org artifact into a local source cache"
    )
    source_fetch_cmd.add_argument("url", help="official iso20022.org URL")
    source_fetch_cmd.add_argument("--out", required=True, help="target file or directory")
    source_fetch_cmd.add_argument(
        "--expected-message-definition",
        help="exact message-definition ID used to verify targetNamespace",
    )
    source_fetch_cmd.add_argument("--expected-checksum", help="optional expected sha256:<hex>")
    source_fetch_cmd.set_defaults(handler=_cmd_source_fetch)

    message_set_discover_cmd = commands.add_parser(
        "message-set-discover",
        help="discover complete message-set download links from the official catalogue",
    )
    message_set_discover_cmd.add_argument("family", help="family or logical ID such as pacs")
    message_set_discover_cmd.set_defaults(handler=_cmd_message_set_discover)

    message_set_fetch_cmd = commands.add_parser(
        "message-set-fetch", help="fetch and safely index one ISO message-set ZIP"
    )
    message_set_fetch_cmd.add_argument("url", help="official ISO message-set download URL")
    message_set_fetch_cmd.add_argument("--out", required=True, help="ignored source cache")
    message_set_fetch_cmd.add_argument("--family", help="family label for reporting")
    message_set_fetch_cmd.add_argument("--message-set-name", help="official message-set name")
    message_set_fetch_cmd.set_defaults(handler=_cmd_message_set_fetch)

    message_set_inspect_cmd = commands.add_parser(
        "message-set-inspect", help="safely inspect and index a local ISO message-set ZIP"
    )
    message_set_inspect_cmd.add_argument("bundle", help="local message-set ZIP")
    message_set_inspect_cmd.add_argument("--sources", required=True, help="ignored source cache")
    message_set_inspect_cmd.add_argument("--family", help="family label for reporting")
    message_set_inspect_cmd.add_argument("--message-set-name", help="official message-set name")
    message_set_inspect_cmd.set_defaults(handler=_cmd_message_set_inspect)

    source_acquire_cmd = commands.add_parser(
        "source-acquire", help="download every xsdUrl in a manifest into a local source cache"
    )
    source_acquire_cmd.add_argument("--manifest", required=True, help="metadata manifest YAML")
    source_acquire_cmd.add_argument("--sources", required=True, help="ignored source cache")
    source_acquire_cmd.add_argument("--out", help="write updated metadata manifest")
    source_acquire_cmd.add_argument(
        "--bundle-only",
        action="store_true",
        help="verify message-set bundles only; skip individual XSD fallback requests",
    )
    source_acquire_cmd.set_defaults(handler=_cmd_source_acquire)

    source_inspect_cmd = commands.add_parser(
        "source-inspect", help="summarise a metadata-only source manifest"
    )
    source_inspect_cmd.add_argument("manifest")
    source_inspect_cmd.set_defaults(handler=_cmd_source_inspect)

    scaleout_cmd = commands.add_parser(
        "scaleout", help="compile and gate every source listed in a manifest"
    )
    scaleout_cmd.add_argument("--manifest", required=True, help="source manifest YAML")
    scaleout_cmd.add_argument(
        "--sources",
        required=True,
        help="directory containing sourceLocation files from the manifest",
    )
    scaleout_cmd.add_argument("--out", required=True, help="directory for candidate packs")
    scaleout_cmd.add_argument("--report", help="write a markdown batch report")
    scaleout_cmd.set_defaults(handler=_cmd_scaleout)

    mt_prowide_extract_cmd = commands.add_parser(
        "mt-prowide-extract",
        help="extract Prowide-derived MT structural evidence",
    )
    mt_prowide_extract_cmd.add_argument("--lock", default=str(DEFAULT_LOCK))
    mt_prowide_extract_cmd.add_argument("--cache", default=str(DEFAULT_CACHE))
    mt_prowide_extract_cmd.add_argument("--out", help="write the extraction fixture JSON")
    mt_prowide_extract_cmd.set_defaults(handler=_cmd_mt_prowide_extract)

    mt_prowide_reports_cmd = commands.add_parser(
        "mt-prowide-reports",
        help="render or check generated MT Prowide reports",
    )
    mt_prowide_reports_cmd.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    mt_prowide_reports_cmd.add_argument("--check", action="store_true")
    mt_prowide_reports_cmd.add_argument("--write", action="store_true")
    mt_prowide_reports_cmd.set_defaults(handler=_cmd_mt_prowide_reports)

    mt_prowide_verify_cmd = commands.add_parser(
        "mt-prowide-verify",
        help="download pinned Prowide jars, refresh-extract, and prove MT541 parsing",
    )
    mt_prowide_verify_cmd.add_argument("--lock", default=str(DEFAULT_LOCK))
    mt_prowide_verify_cmd.add_argument("--cache", default=str(DEFAULT_CACHE))
    mt_prowide_verify_cmd.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    mt_prowide_verify_cmd.add_argument("--out", help="optional path for the fresh extraction")
    mt_prowide_verify_cmd.set_defaults(handler=_cmd_mt_prowide_verify)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
