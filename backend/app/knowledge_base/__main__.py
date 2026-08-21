"""``python -m app.knowledge_base`` — the operator's commands.

sync               discover, identify, segment, index, embed (policy permitting), compile
status             what the knowledge base holds
reindex            sync with every source re-parsed and every structure recompiled
rebuild-structures re-read every guide's structure from the cached text and recompile packs
manifest           write (--write) or verify the committed knowledge-source manifest
clean-cache        remove the ignored caches (never a source document)
probe-embeddings   one synthetic embedding call against the configured deployment
evaluate-rag       the retrieval evaluation over the synthetic corpus
reports            write the generated readiness/coverage documents
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time

from app.config import get_settings
from app.knowledge_base.db import KnowledgeDatabase
from app.knowledge_base.embeddings import EmbeddingError, embedding_provider
from app.knowledge_base.models import SyncProgress
from app.knowledge_base.paths import knowledge_db_path, knowledge_pack_dir, resolve_project_path


def _progress(path: str, report: SyncProgress) -> None:
    print(
        f"  {report.documents_parsed + report.documents_unchanged + report.documents_failed:>4}  "
        f"{path[:80]}",
        flush=True,
    )


def cmd_manifest(args: argparse.Namespace) -> int:
    from app.knowledge_base import manifest

    if args.write:
        path = manifest.write_manifest()
        payload = manifest.load_manifest()
        print(f"wrote {path}: {payload['fileCount']} file(s), {payload['totalBytes']} bytes")
        return 0
    verdict = manifest.verify_manifest(identify=bool(args.identify))
    for problem in verdict.problems[:50]:
        print(f"  {problem}", file=sys.stderr)
    print(
        f"knowledge manifest: {verdict.verified}/{verdict.listed} source file(s) verified"
        + (", identities re-read" if args.identify else "")
    )
    return 0 if verdict.passed else 1


def cmd_rebuild_structures(args: argparse.Namespace) -> int:
    from app.knowledge_base.index import KnowledgeIndexer

    settings = get_settings()
    database = KnowledgeDatabase(knowledge_db_path(settings))
    indexer = KnowledgeIndexer(settings, database, embedding_provider(settings))
    report = indexer.rebuild_structures(progress=_progress if not args.quiet else None)
    for key in (
        "documentsParsed",
        "structuresCompiled",
        "structuresReused",
        "structuresFailed",
        "elapsedMs",
    ):
        print(f"  {key}: {report.as_dict().get(key)}")
    for item in report.failures[:20]:
        print(f"    {item.get('code')}: {item.get('path')} {item.get('detail', '')}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    from app.knowledge_base.index import KnowledgeIndexer, SyncOptions

    settings = get_settings()
    database = KnowledgeDatabase(knowledge_db_path(settings))
    provider = embedding_provider(settings)
    print(
        f"knowledge sync: roots={settings.knowledge_source_dir} "
        f"db={knowledge_db_path(settings).name} "
        f"embeddings={provider.name}{'/' + provider.deployment if provider.deployment else ''}"
    )
    indexer = KnowledgeIndexer(settings, database, provider)
    report = indexer.sync(
        SyncOptions(reindex=bool(args.reindex), embed=not args.no_embed),
        progress=_progress if not args.quiet else None,
    )
    payload = report.as_dict()
    payload.pop("failures", None)
    for key, value in payload.items():
        print(f"  {key}: {value}")
    if report.failures:
        print(f"  failures ({len(report.failures)}):")
        for item in report.failures[:50]:
            print(f"    {item.get('code')}: {item.get('path')} {item.get('detail', '')}")
    if args.reports:
        from app.knowledge_base.reports import write_reports

        for path in write_reports():
            print(f"  wrote {path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    del args
    from app.knowledge_base.service import KnowledgeService

    status = KnowledgeService().status().as_dict()
    print(json.dumps(status, indent=2, sort_keys=True))
    if status["indexed"]:
        from app.knowledge_base.preview import preview_registries

        registries = preview_registries()
        from collections import Counter

        counts = Counter(
            (item.format, item.readiness.value) for item in registries.structures.values()
        )
        print("structures:")
        for (format_name, readiness), count in sorted(counts.items()):
            print(f"  {format_name} {readiness}: {count}")
    return 0


def cmd_clean_cache(args: argparse.Namespace) -> int:
    settings = get_settings()
    targets = [
        resolve_project_path(settings.knowledge_source_cache_dir),
        knowledge_pack_dir(settings),
    ]
    if args.database:
        targets.append(knowledge_db_path(settings))
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
            print(f"removed {target.name}/")
        elif target.is_file():
            target.unlink()
            for suffix in ("-wal", "-shm"):
                sibling = target.with_name(target.name + suffix)
                if sibling.exists():
                    sibling.unlink()
            print(f"removed {target.name}")
    print("source documents were not touched")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """A harmless synthetic string against the configured deployment. Records the adapter,
    the deployment name, the dimension actually returned, latency and usage. No secret."""
    del args
    settings = get_settings()
    provider = embedding_provider(settings)
    print(f"adapter: {provider.name}")
    print(f"deployment: {provider.deployment or '(none)'}")
    if not provider.available:
        print("result: NOT_CONFIGURED")
        return 2
    started = time.monotonic()
    try:
        result = provider.embed(
            [
                "SYNTHETIC PROBE: a fictional settlement instruction used only to test "
                "connectivity.",
                "SYNTHETIC PROBE: a second fictional sentence.",
            ]
        )
    except EmbeddingError as error:
        print(f"result: FAIL {error.code}")
        return 1
    print("result: PASS")
    print(f"model: {result.model}")
    print(f"dimensions: {result.dimensions}")
    print(f"vectors: {len(result.vectors)}")
    print(f"latencyMs: {round((time.monotonic() - started) * 1000)}")
    print(
        f"usage: promptTokens={result.usage.prompt_tokens} totalTokens={result.usage.total_tokens}"
    )
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from app.knowledge_base.evaluation import run_evaluation

    report = run_evaluation(live=bool(args.live))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("passed") else 1


def cmd_reports(args: argparse.Namespace) -> int:
    from app.knowledge_base.reports import stale_reports, write_reports

    if args.check:
        stale = stale_reports()
        if stale:
            for path in stale:
                print(f"stale: {path}")
            return 1
        print("generated knowledge reports are current")
        return 0
    for path in write_reports():
        print(f"wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.knowledge_base")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="incremental sync of the knowledge roots")
    sync.add_argument("--reindex", action="store_true", help="re-parse every source")
    sync.add_argument("--no-embed", action="store_true", help="skip embedding entirely")
    sync.add_argument("--reports", action="store_true", help="write the generated reports")
    sync.add_argument("--quiet", action="store_true")
    sync.set_defaults(func=cmd_sync)

    manifest = sub.add_parser(
        "manifest", help="write or verify swiftKnowledgeBase/source-manifest.json"
    )
    manifest.add_argument("--write", action="store_true", help="write from the synced database")
    manifest.add_argument("--identify", action="store_true", help="also re-read each identity")
    manifest.set_defaults(func=cmd_manifest)

    rebuild = sub.add_parser(
        "rebuild-structures", help="re-read guide structures from cached text; recompile packs"
    )
    rebuild.add_argument("--quiet", action="store_true")
    rebuild.set_defaults(func=cmd_rebuild_structures)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    clean = sub.add_parser("clean-cache")
    clean.add_argument("--database", action="store_true", help="also remove the knowledge DB")
    clean.set_defaults(func=cmd_clean_cache)

    probe = sub.add_parser("probe-embeddings")
    probe.set_defaults(func=cmd_probe)

    evaluate = sub.add_parser("evaluate-rag")
    evaluate.add_argument("--live", action="store_true", help="use the configured embeddings")
    evaluate.set_defaults(func=cmd_evaluate)

    reports = sub.add_parser("reports")
    reports.add_argument("--check", action="store_true")
    reports.set_defaults(func=cmd_reports)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
