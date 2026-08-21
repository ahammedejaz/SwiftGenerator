"""``python -m app.mapping evidence --scan | --write | --check``
``python -m app.mapping packs --refresh-checksums | --check-checksums``

scan   sweep the local knowledge base for MT ↔ ISO 20022 correspondence vocabulary and
       write the evidence index (identities and pages, no text)
write  run the conversion proofs locally and render docs/generated/mt-mx-mapping-coverage.md
check  re-render the report from the committed index and proofs; fail if it drifted

packs  a Mapping Pack pins the checksum of the two message specifications it was written
       against, so that a pack cannot keep executing after a structure moved underneath it.
       Any change to the specification projection therefore invalidates every pack at once.
       ``--refresh-checksums`` rewrites them from the current projection — review the diff,
       because the gate exists to make you look. ``--check-checksums`` only reports.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.mapping")
    sub = parser.add_subparsers(dest="command", required=True)
    evidence = sub.add_parser("evidence", help="mapping evidence index and coverage report")
    evidence.add_argument("--scan", action="store_true", help="sweep the knowledge base")
    evidence.add_argument("--write", action="store_true", help="run proofs and render")
    evidence.add_argument("--check", action="store_true", help="check the rendered report")
    packs = sub.add_parser("packs", help="Mapping Pack structure checksums")
    packs.add_argument("--refresh-checksums", action="store_true", help="rewrite them")
    packs.add_argument("--check-checksums", action="store_true", help="report only")
    args = parser.parse_args(argv)

    if args.command == "packs":
        from app.mapping.checksums import refresh_pack_checksums

        drifted = refresh_pack_checksums(write=bool(args.refresh_checksums))
        for pack_path, which, before, after in drifted:
            verb = "updated" if args.refresh_checksums else "is stale"
            print(f"{pack_path.name}: {which} {verb} ({before[:12]} -> {after[:12]})")
        if not drifted:
            print("Every Mapping Pack structure checksum matches the current projection")
            return 0
        return 0 if args.refresh_checksums else 1

    from app.mapping import evidence as module

    if args.scan:
        index = module.scan_knowledge_base()
        path = module.write_index(index)
        print(
            f"wrote {path}: {index.sources_scanned} source(s), {index.segments_scanned} "
            f"segment(s), {len(index.hits)} hit(s)"
        )
    if args.write or args.scan:
        for path in module.write_reports(run=True):
            print(f"wrote {path}")
        return 0
    stale = module.stale_reports()
    if stale:
        for path in stale:
            print(f"{path} is stale", file=sys.stderr)
        return 1
    print("MT→MX mapping coverage report is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
