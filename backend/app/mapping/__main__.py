"""``python -m app.mapping evidence --scan | --write | --check``

scan   sweep the local knowledge base for MT ↔ ISO 20022 correspondence vocabulary and
       write the evidence index (identities and pages, no text)
write  run the conversion proofs locally and render docs/generated/mt-mx-mapping-coverage.md
check  re-render the report from the committed index and proofs; fail if it drifted
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
    args = parser.parse_args(argv)

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
