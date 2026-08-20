"""The rule-engine CLI — the developer front door.

    python -m app.rule_engine ingest   SOURCE_ID [--stamp]
    python -m app.rule_engine extract  --source-id ID --message sese.023 [--layer ...]
    python -m app.rule_engine review   CANDIDATE.yaml --approve --reviewer NAME
    python -m app.rule_engine validate PACK.yaml
    python -m app.rule_engine inspect  [--message sese.023] [--profile BASE_DEMO_V1]
    python -m app.rule_engine diff     BEFORE.yaml AFTER.yaml
    python -m app.rule_engine evaluate [--live]
    python -m app.rule_engine mrg-inspect
    python -m app.rule_engine mrg-extract  [--out FIXTURE.json]
    python -m app.rule_engine mrg-reports  --write | --check
    python -m app.rule_engine mrg-evaluate
    python -m app.rule_engine mrg-verify

Extraction is offline by design. The running application never extracts a rule, never
compiles a candidate and never writes to the rules directory: a reviewed pack becomes
active the way any configuration does — reviewed, committed, loaded at startup.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from app.config import get_settings
from app.knowledge.models import RuleLayer
from app.rule_engine.compiler import compile_pack
from app.rule_engine.diagnostics import RuleEngineError
from app.rule_engine.extraction.cache import ExtractionCache
from app.rule_engine.extraction.pipeline import RuleExtractionPipeline
from app.rule_engine.extraction.provider import configured_models, live_client
from app.rule_engine.extraction.review import (
    ReviewAction,
    apply_review,
    candidate_hashes,
    pack_yaml,
    review_package,
)
from app.rule_engine.models import RulePack
from app.rule_engine.packdiff import diff_packs
from app.rule_engine.refs import StructureIndex
from app.rule_engine.registry import RulePackRegistry, rule_pack_directory
from app.rule_engine.sources import SourceManifest, rule_source_directory
from app.studio.models import MessageFormat


def _index() -> StructureIndex:
    return StructureIndex()


def _read_pack(path: Path) -> RulePack:
    return RulePack.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _cmd_ingest(args: argparse.Namespace) -> int:
    manifest = SourceManifest(Path(args.directory) if args.directory else None)
    try:
        ingested = manifest.ingest(args.source_id)
    except (KeyError, RuleEngineError) as error:
        if isinstance(error, RuleEngineError):
            for finding in error.findings:
                print(finding.render(), file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1
    print(f"source:    {ingested.bundle.source_id} ({ingested.bundle.title})")
    print(f"declared:  {ingested.bundle.source_type.value} — an operator declaration")
    print(f"adapter:   {ingested.adapter.value}")
    print(f"checksum:  {ingested.checksum}")
    print(f"segments:  {len(ingested.segments)}")
    if ingested.page_count:
        print(f"pages:     {ingested.page_count}")
    for segment in ingested.segments:
        heading = segment.heading or "-"
        print(
            f"  {segment.segment_id}  lines {segment.line_start}-{segment.line_end}"
            f"  [{heading}]  {segment.segment_hash[:19]}…"
        )
    if args.stamp:
        print(
            "\nRecord this in the manifest so a later change to the document is detected:"
            f"\n  sourceChecksum: {ingested.checksum}"
        )
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    settings = get_settings()
    manifest = SourceManifest(Path(args.directory) if args.directory else None)
    try:
        ingested = manifest.ingest(args.source_id)
    except (KeyError, RuleEngineError) as error:
        if isinstance(error, RuleEngineError):
            for finding in error.findings:
                print(finding.render(), file=sys.stderr)
        else:
            print(str(error), file=sys.stderr)
        return 1

    if not ingested.bundle.external_model_processing_allowed():
        print(
            "RULE_EXTRACTION_PRIVACY_BLOCKED — this source is not approved for external "
            "model processing. Local ingestion and segmentation are available, but LLM "
            "extraction requires sourceAllowsExternalModelProcessing and "
            "providerApprovedForSourceClassification to be explicitly true.",
            file=sys.stderr,
        )
        return 2

    client = live_client(settings)
    if client is None:
        print(
            "RULE_EXTRACTION_UNAVAILABLE — no approved model provider is configured, so no "
            "candidate can be produced. Everything already installed keeps working; only "
            "new extraction is unavailable.",
            file=sys.stderr,
        )
        return 2

    index = _index()
    format_ = MessageFormat(args.format)
    if not index.known(format_, args.message):
        print(f"{args.message} is not an installed {format_} message.", file=sys.stderr)
        return 1

    cache = ExtractionCache(
        directory=Path(settings.rule_extraction_cache_directory),
        enabled=settings.rule_extraction_cache_enabled,
    )
    pipeline = RuleExtractionPipeline(
        client,
        index,
        models=configured_models(settings),
        cache=cache,
        max_fields=settings.rule_extraction_max_fields,
    )

    async def go() -> object:
        try:
            return await pipeline.run(
                ingested,
                format_=format_,
                message_type=args.message,
                layer=RuleLayer(args.layer),
                profile_id=args.profile,
            )
        finally:
            await client.aclose()

    run = asyncio.run(go())
    out = Path(args.out) if args.out else Path(settings.rule_candidate_directory)
    out.mkdir(parents=True, exist_ok=True)
    pack = run.candidate_pack(index)  # type: ignore[attr-defined]
    stem = f"{args.source_id.lower()}-{args.message.replace('.', '_')}"
    (out / f"{stem}-review.md").write_text(
        review_package(run),  # type: ignore[arg-type]
        encoding="utf-8",
    )
    if pack is not None:
        (out / f"{stem}-candidate.yaml").write_text(pack_yaml(pack), encoding="utf-8")
    metrics = run.metrics()  # type: ignore[attr-defined]
    print(f"segments:  {metrics['segmentsProcessed']}")
    print(f"calls:     {metrics['liveCalls']} live, {metrics['cacheHits']} cached")
    print(f"tokens:    {metrics['tokensUsed']} (as reported by the provider)")
    print(f"accepted:  {metrics['candidatesAccepted']}  rejected: {metrics['candidatesRejected']}")
    print(f"agreement: {metrics['agreement']}")
    print(f"written:   {out}/{stem}-review.md")
    if pack is not None:
        print(f"           {out}/{stem}-candidate.yaml")
    print(
        "\nNothing above is installed. Read the review package, then approve with\n"
        f"  python -m app.rule_engine review {out}/{stem}-candidate.yaml --approve "
        '--reviewer "Your Name"'
    )
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    path = Path(args.candidate)
    pack = _read_pack(path)
    hashes = candidate_hashes(pack)
    if args.edited:
        pack = _read_pack(Path(args.edited))
    action = (
        ReviewAction.APPROVE
        if args.approve
        else ReviewAction.REJECT
        if args.reject
        else ReviewAction.DEFER
    )
    try:
        reviewed = apply_review(
            pack,
            action,
            reviewer=args.reviewer or "",
            reason=args.reason or "",
            candidate_hashes=hashes,
        )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1

    if action is ReviewAction.APPROVE:
        try:
            compile_pack(reviewed, _index(), require_reviewed=True)
        except RuleEngineError as error:
            for finding in error.findings:
                print(finding.render(), file=sys.stderr)
            print(
                "\nThe pack was not written: an approved pack must compile against the "
                "installed structure.",
                file=sys.stderr,
            )
            return 1

    out_dir = Path(args.out) if args.out else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / reviewed.file_name()
    target.write_text(pack_yaml(reviewed), encoding="utf-8")
    print(f"{action.value}: wrote {target}")
    if action is ReviewAction.APPROVE:
        print(
            "Approval here is not activation. Commit this file, open a pull request, and "
            f"let CI run; the registry loads it from {rule_pack_directory()} only after "
            "it is merged."
        )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.pack)
    try:
        pack = _read_pack(path)
    except Exception as error:  # noqa: BLE001 - any parse failure is one outcome here
        print(f"{path.name} is not a readable rule pack: {error}", file=sys.stderr)
        return 1
    try:
        compiled = compile_pack(pack, _index(), require_reviewed=args.require_reviewed)
    except RuleEngineError as error:
        for finding in error.findings:
            print(finding.render(), file=sys.stderr)
        return 1
    for warning in compiled.warnings:
        print(warning.render(), file=sys.stderr)
    print(f"{pack.pack_id}: {len(compiled.rules)} rule(s), "
          f"{len(compiled.restrictions)} code restriction(s) — compiles")
    print(f"structure: {pack.structure_compatibility.structure_checksum}")
    print(f"review:    {pack.review.status.value}"
          + ("" if pack.fully_reviewed() else " — not loadable until fully reviewed"))
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    registry = RulePackRegistry(index=_index())
    print(f"rules directory: {registry.directory}")
    print(f"source directory: {rule_source_directory()}")
    packs = registry.packs()
    if not packs:
        print("no rule packs installed")
    for compiled in packs:
        pack = compiled.pack
        print(
            f"  {pack.pack_id}  {len(compiled.rules)} rule(s), "
            f"{len(compiled.restrictions)} restriction(s)"
        )
    for warning in registry.warnings:
        print(f"  {warning.render()}")
    if args.message:
        format_ = MessageFormat(args.format)
        from app.profiles.loader import profiles

        for profile in profiles.list():
            if args.profile and profile.profile_id != args.profile:
                continue
            effective = registry.effective(format_, args.message, profile.profile_id)
            layers = ", ".join(item.value for item in effective.layers_present()) or "none"
            print(
                f"\n{args.message} under {profile.profile_id}: {len(effective.rules)} "
                f"rule(s), {len(effective.restrictions)} restriction(s); layers: {layers}"
            )
            for rule in effective.rules:
                print(f"  [{rule.layer.value}] {rule.rule.rule_id} — {rule.rule.title}")
            for entry in effective.restrictions:
                restriction = entry.compiled.restriction
                print(
                    f"  [{entry.layer.value}] {restriction.restriction_id} — "
                    f"{entry.field.display_name} limited to {', '.join(restriction.codes)}"
                )
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    result = diff_packs(_read_pack(Path(args.before)), _read_pack(Path(args.after)))
    print(result.render())
    return 0 if result.identical else 2


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from app.rule_engine.evaluation.runner import run_evaluation

    report = run_evaluation(
        live=args.live,
        corpus_path=Path(args.corpus) if args.corpus else None,
    )
    print(report.render())
    return 0 if report.passed else 1


def _cmd_mt_readiness(args: argparse.Namespace) -> int:
    from app.rule_engine.mt_semantics import (
        check_reports,
        render_semantic_readiness,
        render_source_readiness,
        write_reports,
    )

    if args.write:
        write_reports()
        print("MT semantic readiness reports written")
        return 0
    if args.check:
        if check_reports():
            print("MT semantic readiness reports are current")
            return 0
        print("MT semantic readiness reports are stale", file=sys.stderr)
        return 1
    print(render_semantic_readiness())
    print(render_source_readiness())
    return 0


def _cmd_mrg_inspect(args: argparse.Namespace) -> int:
    from app.rule_engine.mt_mrg.pipeline import MrgSourceCatalogue, run

    catalogue = MrgSourceCatalogue(
        directory=Path(args.directory) if args.directory else None
    )
    print(f"manifest:  {catalogue._path}")  # noqa: SLF001 - the CLI reports its own inputs
    print(f"drop:      {catalogue.directory}")
    present = [item for item in catalogue.ids() if catalogue.present(item)]
    for source_id in catalogue.ids():
        bundle = catalogue.get(source_id)
        state = "present" if source_id in present else "SOURCE_NOT_AVAILABLE"
        print(
            f"  {source_id}  {bundle.standards_release}  "
            f"{', '.join(bundle.message_identifiers)}  {state}"
        )
        print(f"      declared:  {bundle.source_type.value} — an operator declaration")
        print(f"      external model processing: "
              f"{'ALLOWED' if bundle.external_model_processing_allowed() else 'BLOCKED'}")
    if not present:
        print(
            "\nNo Message Reference Guide is present. Everything derived from them is "
            "already committed; only re-reading them is unavailable."
        )
        return 0
    outcome = run(catalogue)
    for source_id, reason in outcome.unreadable:
        print(f"\n  {source_id}: SOURCE_UNREADABLE — {reason}", file=sys.stderr)
    for reading in outcome.readings:
        print()
        for key, value in reading.metrics().items():
            print(f"  {key}: {value}")
        if reading.problems:
            print(f"  problems: {', '.join(reading.problems)}")
    return 0 if outcome.readings or not outcome.unreadable else 2


def _cmd_mrg_extract(args: argparse.Namespace) -> int:
    from app.rule_engine.mt_mrg import fixture
    from app.rule_engine.mt_mrg.pipeline import MrgSourceCatalogue, run

    catalogue = MrgSourceCatalogue(
        directory=Path(args.directory) if args.directory else None
    )
    outcome = run(catalogue)
    if not outcome.readings:
        for source_id, reason in outcome.unreadable:
            print(f"{source_id}: SOURCE_UNREADABLE — {reason}", file=sys.stderr)
        print(
            "SOURCE_NOT_AVAILABLE — no Message Reference Guide could be read from "
            f"{catalogue.directory}.",
            file=sys.stderr,
        )
        return 2
    target = fixture.write(outcome, Path(args.out) if args.out else None)
    print(f"read:      {', '.join(item.source_id for item in outcome.readings)}")
    print(f"wrote:     {target}")
    candidates = sum(len(item.pack.rules) if item.pack else 0 for item in outcome.readings)
    print(f"candidates: {candidates} — all REVIEW_REQUIRED, none installed")
    return 0


def _cmd_mrg_reports(args: argparse.Namespace) -> int:
    from app.rule_engine.mt_mrg import reports

    if args.write:
        for path in reports.write_reports():
            print(f"wrote {path}")
        return 0
    stale = reports.stale_reports()
    if stale:
        for path in stale:
            print(f"{path} is stale", file=sys.stderr)
        print("Run `make mt-mrg-reports-write`.", file=sys.stderr)
        return 1
    print("MT MRG generated reports are current")
    return 0


def _cmd_mrg_evaluate(args: argparse.Namespace) -> int:
    from app.rule_engine.mt_mrg.evaluation import ANCHOR_CASES, run_cases
    from app.rule_engine.mt_mrg.pipeline import MrgSourceCatalogue, run

    catalogue = MrgSourceCatalogue(
        directory=Path(args.directory) if args.directory else None
    )
    outcome = run(catalogue)
    if not outcome.readings:
        for source_id, reason in outcome.unreadable:
            print(f"{source_id}: SOURCE_UNREADABLE — {reason}", file=sys.stderr)
        print(
            "SOURCE_NOT_AVAILABLE — candidate evaluation needs the Message Reference "
            "Guides, which are licensed and never committed.",
            file=sys.stderr,
        )
        return 2
    report = run_cases(
        {item.identity.message_type: item for item in outcome.readings}, ANCHOR_CASES
    )
    print(report.render())
    return 0 if report.passed else 1


def _cmd_mrg_verify(args: argparse.Namespace) -> int:
    """Re-read the guides and prove the committed evidence still describes them."""
    from app.rule_engine.mt_mrg import fixture
    from app.rule_engine.mt_mrg.pipeline import MrgSourceCatalogue, run

    catalogue = MrgSourceCatalogue(
        directory=Path(args.directory) if args.directory else None
    )
    outcome = run(catalogue)
    if not outcome.readings:
        for source_id, reason in outcome.unreadable:
            print(f"  {source_id}: SOURCE_UNREADABLE — {reason}")
        print(
            "SOURCE_NOT_AVAILABLE — the SWIFT Message Reference Guides are licensed and "
            "are never committed, so this proof runs only where an operator has dropped "
            f"them into {catalogue.directory} and installed a PDF text extractor. "
            "Everything derived from them is committed and is checked by "
            "`make mt-mrg-check`.",
        )
        return 0
    fresh = fixture.build(outcome)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(fixture.render(fresh), encoding="utf-8")
        print(f"wrote {target}")
    committed = fixture.load()
    for reading in outcome.readings:
        print(
            f"  {reading.source_id}  {reading.identity.message_type}  "
            f"{reading.identity.standards_release}  {reading.page_count} pages  "
            f"{reading.checksum}"
        )
    if fixture.render(fresh) != fixture.render(committed):
        print(
            "\nThe guides no longer produce the committed evidence. Re-run "
            "`make mt-mrg-extract`, re-read every candidate, and say in the commit what "
            "changed.",
            file=sys.stderr,
        )
        return 1
    print("\nThe committed evidence reproduces exactly from the operator's documents.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.rule_engine", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="read and segment a declared source")
    ingest.add_argument("source_id")
    ingest.add_argument("--directory", help="drop directory (default: the configured one)")
    ingest.add_argument(
        "--stamp", action="store_true", help="print the checksum to record in the manifest"
    )
    ingest.set_defaults(handler=_cmd_ingest)

    extract = commands.add_parser("extract", help="propose candidate rules from a source")
    extract.add_argument("--source-id", required=True)
    extract.add_argument("--message", required=True)
    extract.add_argument("--format", default="MX", choices=[item.value for item in MessageFormat])
    extract.add_argument(
        "--layer",
        default=RuleLayer.BASE_STANDARD.value,
        choices=[
            RuleLayer.BASE_STANDARD.value,
            RuleLayer.MARKET_PRACTICE.value,
            RuleLayer.CLIENT_PROFILE.value,
        ],
    )
    extract.add_argument("--profile", help="profile a market or client pack serves")
    extract.add_argument("--directory", help="drop directory")
    extract.add_argument("--out", help="where to write the candidate and review package")
    extract.set_defaults(handler=_cmd_extract)

    review = commands.add_parser("review", help="approve, reject or defer a candidate pack")
    review.add_argument("candidate")
    review.add_argument("--approve", action="store_true")
    review.add_argument("--reject", action="store_true")
    review.add_argument("--defer", action="store_true")
    review.add_argument("--reviewer", help="who is accountable for the decision")
    review.add_argument("--reason", help="why a candidate was rejected")
    review.add_argument("--edited", help="an edited copy to approve instead of the original")
    review.add_argument("--out", help="directory to write the reviewed pack into")
    review.set_defaults(handler=_cmd_review)

    validate = commands.add_parser("validate", help="compile a pack against installed structure")
    validate.add_argument("pack")
    validate.add_argument(
        "--require-reviewed",
        action="store_true",
        help="also require every rule to be reviewed, as the registry does",
    )
    validate.set_defaults(handler=_cmd_validate)

    inspect = commands.add_parser("inspect", help="what is installed, and what applies")
    inspect.add_argument("--message")
    inspect.add_argument("--profile")
    inspect.add_argument("--format", default="MX", choices=[item.value for item in MessageFormat])
    inspect.set_defaults(handler=_cmd_inspect)

    diff = commands.add_parser("diff", help="deterministic diff of two rule packs")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.set_defaults(handler=_cmd_diff)

    evaluate = commands.add_parser("evaluate", help="run the extraction evaluation corpus")
    evaluate.add_argument(
        "--live",
        action="store_true",
        help="call the configured models instead of the scripted ones. Costs money.",
    )
    evaluate.add_argument("--corpus", help="evaluation corpus YAML (default: configured)")
    evaluate.set_defaults(handler=_cmd_evaluate)

    mt_readiness = commands.add_parser(
        "mt-readiness", help="render or check MT semantic readiness reports"
    )
    mt_readiness.add_argument("--write", action="store_true", help="write generated docs")
    mt_readiness.add_argument("--check", action="store_true", help="check generated docs")
    mt_readiness.set_defaults(handler=_cmd_mt_readiness)

    mrg_inspect = commands.add_parser(
        "mrg-inspect", help="which Message Reference Guides are declared and present"
    )
    mrg_inspect.add_argument("--directory", help="drop directory holding the guides")
    mrg_inspect.set_defaults(handler=_cmd_mrg_inspect)

    mrg_extract = commands.add_parser(
        "mrg-extract", help="read the guides into the committed evidence fixture"
    )
    mrg_extract.add_argument("--directory", help="drop directory holding the guides")
    mrg_extract.add_argument("--out", help="fixture path (default: the committed one)")
    mrg_extract.set_defaults(handler=_cmd_mrg_extract)

    mrg_reports = commands.add_parser(
        "mrg-reports", help="render or check the generated MRG reports"
    )
    mrg_reports.add_argument("--write", action="store_true")
    mrg_reports.add_argument("--check", action="store_true")
    mrg_reports.set_defaults(handler=_cmd_mrg_reports)

    mrg_evaluate = commands.add_parser(
        "mrg-evaluate", help="prove candidate rules against synthetic values"
    )
    mrg_evaluate.add_argument("--directory", help="drop directory holding the guides")
    mrg_evaluate.set_defaults(handler=_cmd_mrg_evaluate)

    mrg_verify = commands.add_parser(
        "mrg-verify", help="prove the committed evidence reproduces from the real guides"
    )
    mrg_verify.add_argument("--directory", help="drop directory holding the guides")
    mrg_verify.add_argument("--out", help="write the fresh fixture here for comparison")
    mrg_verify.set_defaults(handler=_cmd_mrg_verify)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
