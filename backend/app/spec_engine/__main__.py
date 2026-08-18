"""The specification engine CLI — the developer front door.

    .venv/bin/python -m app.spec_engine compile SOURCE.xsd [--out DIR] [--root NAME]
    .venv/bin/python -m app.spec_engine validate PACK.yaml --source SOURCE.xsd
    .venv/bin/python -m app.spec_engine inspect SOURCE.xsd
    .venv/bin/python -m app.spec_engine diff BEFORE.yaml AFTER.yaml

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
from app.spec_engine.pipeline import compile_schema
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
        default="OFFICIAL_ISO_20022_XSD",
        help="provenance label recorded in the pack (declare honestly)",
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

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
