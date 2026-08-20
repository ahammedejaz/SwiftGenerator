from __future__ import annotations

import json
import re
from pathlib import Path

from app.spec_engine.mt_prowide.java_probe import field_definitions, parse_fin
from app.spec_engine.mt_prowide.models import (
    AuthoringReadinessStatus,
    CandidateStructureState,
    MtCrossEngineResult,
    MtMessageEvidence,
    MtProwideExtraction,
    ProwideParsedTag,
)
from app.spec_engine.mt_prowide.source import (
    DEFAULT_CACHE,
    DEFAULT_FIXTURE,
    DEFAULT_LOCK,
    ensure_artifacts,
)
from app.spec_engine.mt_prowide.source_scheme import (
    discovered_categories,
    extract_message_schemes,
)

_BLOCK4_TAG = re.compile(r"^:(?P<tag>\d{2}[A-Z]?):(?P<value>.*)$")

LIMITATIONS = [
    "Prowide Core is used as Prowide-derived structural evidence only; it is not Swift "
    "certification, conformance, validation, or proof of full UHB completeness.",
    "The normal Python/FastAPI runtime does not load Java, Prowide, Maven, or Gradle.",
    "Global Prowide field classes are stored separately from message-level field groups; "
    "global class existence never makes a field mandatory or legal in a message.",
    "Qualifier legality, code-list legality, network validation, market practice, client "
    "rules, and full message-level field permission remain UNKNOWN without reviewed "
    "authoritative sources.",
    "SR2026 Prowide artifacts and Swift SR 2026 material are treated as future/test "
    "release evidence until Swift's 14 November 2026 live date.",
]


def extract_all_categories(
    *,
    lock_path: Path = DEFAULT_LOCK,
    cache_dir: Path = DEFAULT_CACHE,
) -> MtProwideExtraction:
    artifacts = ensure_artifacts(lock_path, cache_dir)
    configured = _configured_mt_types()
    messages = [
        _with_authoring_state(message, installed=message.message_type in configured)
        for message in extract_message_schemes(artifacts.source_jar)
    ]
    tags = sorted({tag for message in messages for tag in message.distinct_tags})
    global_fields = field_definitions(artifacts, tags)
    candidate_messages = [
        message.message_type for message in messages if message.message_type not in configured
    ]
    categories = discovered_categories(artifacts.source_jar)
    category_counts = {
        str(category): sum(1 for message in messages if message.category == category)
        for category in categories
    }
    return MtProwideExtraction(
        source=artifacts.lock,
        extracted_scope="Prowide MT source classes discovered from pinned source jar",
        selected_message_count=len(messages),
        discovered_categories=categories,
        category_counts=category_counts,
        messages=messages,
        global_fields=global_fields,
        activated_messages=[],
        candidate_messages=candidate_messages,
        limitations=LIMITATIONS,
    )


def extract_category5(
    *,
    lock_path: Path = DEFAULT_LOCK,
    cache_dir: Path = DEFAULT_CACHE,
) -> MtProwideExtraction:
    artifacts = ensure_artifacts(lock_path, cache_dir)
    configured = _configured_mt_types()
    messages = [
        _with_authoring_state(message, installed=message.message_type in configured)
        for message in extract_message_schemes(artifacts.source_jar, category=5)
    ]
    tags = sorted({tag for message in messages for tag in message.distinct_tags})
    global_fields = field_definitions(artifacts, tags)
    candidate_messages = [
        message.message_type for message in messages if message.message_type not in configured
    ]
    return MtProwideExtraction(
        source=artifacts.lock,
        extracted_scope="Prowide Category 5 MT classes",
        selected_message_count=len(messages),
        discovered_categories=[5],
        category_counts={"5": len(messages)},
        messages=messages,
        global_fields=global_fields,
        activated_messages=[],
        candidate_messages=candidate_messages,
        limitations=LIMITATIONS,
    )


def load_extraction(path: Path = DEFAULT_FIXTURE) -> MtProwideExtraction:
    return MtProwideExtraction.model_validate_json(path.read_text(encoding="utf-8"))


def write_extraction(extraction: MtProwideExtraction, path: Path = DEFAULT_FIXTURE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(extraction), encoding="utf-8")


def canonical_json(extraction: MtProwideExtraction) -> str:
    payload = extraction.model_dump(by_alias=True, mode="json", exclude_none=True)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def verify_fixture_against_source(
    *,
    fixture: Path = DEFAULT_FIXTURE,
    lock_path: Path = DEFAULT_LOCK,
    cache_dir: Path = DEFAULT_CACHE,
) -> tuple[bool, MtProwideExtraction]:
    fresh = extract_all_categories(lock_path=lock_path, cache_dir=cache_dir)
    expected = fixture.read_text(encoding="utf-8") if fixture.exists() else ""
    return canonical_json(fresh) == expected, fresh


def cross_engine_mt541(
    *,
    lock_path: Path = DEFAULT_LOCK,
    cache_dir: Path = DEFAULT_CACHE,
) -> MtCrossEngineResult:
    from app.profiles.loader import profiles
    from app.studio.models import MessageFormat, SampleVariant
    from app.studio.mt.generator import mt_generator
    from app.studio.mt.parser import parse_message
    from app.studio.samples import build_sample

    message_type = "MT541"
    sample = build_sample(MessageFormat.MT, message_type, SampleVariant.TYPICAL)
    generated = mt_generator.build(
        message_type,
        profiles.get("BASE_DEMO_V1"),
        list(sample.inputs),
        want_fin=True,
    )
    fin = generated.fin or "{2:MT541}\n{4:\n" + generated.block_4 + "\n-}"
    python_tags = _block4_tags(generated.block_4)
    parsed = parse_message(fin)
    artifacts = ensure_artifacts(lock_path, cache_dir)
    prowide = parse_fin(artifacts, message_type, fin)
    prowide_tags = [(tag.tag, tag.value) for tag in prowide.tags]
    return MtCrossEngineResult(
        message_type=message_type,
        source_version=artifacts.lock.prowidesoftware_version,
        tag_stream_identical=python_tags == prowide_tags,
        python_tag_count=len(python_tags),
        prowide_tag_count=prowide.tag_count,
        python_import_errors=len(parsed.errors),
        python_import_warnings=len(parsed.warnings),
        prowide=prowide,
    )


def _block4_tags(block4: str) -> list[tuple[str, str]]:
    tags: list[tuple[str, str]] = []
    for line in block4.splitlines():
        if line in {"{4:", "-}"}:
            continue
        match = _BLOCK4_TAG.match(line)
        if match:
            tags.append((match.group("tag"), match.group("value")))
        elif tags and line:
            tag, value = tags[-1]
            tags[-1] = (tag, value + "\n" + line)
    return tags


def _configured_mt_types() -> set[str]:
    from app.specifications.registry import specification_registry

    return {message.message_type for message in specification_registry.list()}


def _with_authoring_state(message: MtMessageEvidence, *, installed: bool) -> MtMessageEvidence:
    if installed:
        return message.model_copy(
            update={
                "structure_states": [
                    CandidateStructureState.SOURCE_DISCOVERED,
                    CandidateStructureState.STRUCTURE_EXTRACTED,
                    CandidateStructureState.INSTALLED,
                ],
                "authoring_status": AuthoringReadinessStatus.PARTIAL,
                "authoring_blockers": [
                    "AUTHORITATIVE_COMPLETENESS_UNKNOWN",
                    "NETWORK_RULES_UNKNOWN",
                    "MARKET_PRACTICE_UNKNOWN",
                ],
            }
        )
    return message.model_copy(
        update={
            "structure_states": [
                CandidateStructureState.SOURCE_DISCOVERED,
                CandidateStructureState.STRUCTURE_EXTRACTED,
            ],
            "authoring_status": AuthoringReadinessStatus.STRUCTURAL_EVIDENCE_ONLY,
            "authoring_blockers": [
                "NO_RUNTIME_SPECIFICATION",
                "REQUIREDNESS_REVIEW_MISSING",
                "QUALIFIER_RULES_UNKNOWN",
                "CODE_LIST_RULES_UNKNOWN",
                "BUSINESS_RULE_SOURCE_MISSING",
                "SAMPLE_MISSING",
            ],
        }
    )


def parsed_tag_stream(result: MtCrossEngineResult) -> list[ProwideParsedTag]:
    return result.prowide.tags
