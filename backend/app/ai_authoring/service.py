"""The authoring operations. Deterministic first, cache second, model last — and the model's
answer re-enters the ordinary engine as a plain ``GenerateRequest``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.ai_authoring import OUTPUT_SCHEMA_VERSION, PROMPT_VERSION
from app.ai_authoring.prompts import (
    BOUNDARY,
    fence_evidence,
    fence_user,
    seed_block,
    structure_block,
)
from app.ai_authoring.provider import AiUnavailable, AiUsage, authoring_provider
from app.ai_authoring.schemas import (
    answer_schema,
    canonical_values_schema,
    comparison_schema,
    identify_schema,
    negative_schema,
    presentation_schema,
    scenarios_schema,
)
from app.config import get_settings
from app.knowledge_base.models import Citation, QueryType, RetrievalFilter, SourceFormat
from app.knowledge_base.service import knowledge_service
from app.studio.catalogue import build_catalogue, message_spec
from app.studio.models import (
    CatalogueEntry,
    ElementInput,
    FieldInput,
    GenerateRequest,
    GenerateResult,
    Lane,
    MessageFormat,
    MessageSpec,
    OutputMode,
    Presence,
    SampleVariant,
    SpecField,
)
from app.studio.samples import available_variants, build_sample
from app.studio.service import UnknownMessageType, studio_service

TOKEN = re.compile(r"[a-z0-9][a-z0-9.]+")
STOP = frozenset(
    "the a an of to for and or in on with i we need want please create make generate send "
    "message test against by from at as is it this that be my our".split()
)


class AuthoringError(Exception):
    def __init__(self, code: str, detail: str, *, status: int = 422, **extra: Any) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status
        self.extra = extra


# -- evidence ------------------------------------------------------------------------------


@dataclass
class Evidence:
    citations: list[Citation]
    texts: dict[str, str]
    allow_text: bool
    semantic_available: bool
    semantic_reason: str | None
    latency_ms: int
    context_chars: int
    corpus_version: str
    lexical_candidates: int
    semantic_candidates: int

    def prompt(self) -> str:
        return fence_evidence(self.citations, self.texts, allow_text=self.allow_text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "segmentsUsed": len(self.citations),
            "semanticAvailable": self.semantic_available,
            "semanticReason": self.semantic_reason,
            "textSentToModel": self.allow_text,
            "latencyMs": self.latency_ms,
            "contextChars": self.context_chars,
            "corpusVersion": self.corpus_version or None,
            "citations": [_citation_dict(item) for item in self.citations],
        }


def _citation_dict(item: Citation) -> dict[str, Any]:
    return {
        "sourceId": item.source_id,
        "documentTitle": item.document_title,
        "messageType": item.message_type,
        "messageVersion": item.message_version,
        "release": item.release,
        "section": item.section.value,
        "page": item.page,
        "heading": item.heading,
        "segmentId": item.segment_id,
        "segmentHash": item.segment_hash,
        "score": item.score,
        "method": item.method.value,
        "snippet": item.snippet,
    }


def gather_evidence(
    query: str,
    *,
    query_type: QueryType,
    format_: MessageFormat | None,
    message_type: str | None,
    release: str | None,
    limit: int = 8,
) -> Evidence:
    source_format = None
    if format_ is not None:
        source_format = SourceFormat.MT if format_ is MessageFormat.MT else SourceFormat.MX
    version = None
    logical = message_type
    if format_ is MessageFormat.MX and message_type and message_type.count(".") >= 3:
        version = message_type.lower()
        logical = ".".join(version.split(".")[:2])
    if format_ is MessageFormat.MX and release and release.count(".") >= 3:
        version = release.lower()
        release = None
    result = knowledge_service.retrieve(
        query,
        query_type=query_type,
        filter=RetrievalFilter(
            format=source_format,
            message_type=(
                logical.upper() if logical and source_format is SourceFormat.MT else logical
            ),
            message_version=version,
            release=release,
        ),
    )
    hits = result.hits[:limit]
    result.hits = hits
    citations = knowledge_service.citations(result)
    allow = knowledge_service.llm_allowed({item.source_id for item in citations})
    texts = {hit.segment.segment_id: hit.segment.text for hit in hits} if allow else {}
    return Evidence(
        citations=citations,
        texts=texts,
        allow_text=allow,
        semantic_available=result.semantic_available,
        semantic_reason=result.semantic_reason,
        latency_ms=result.latency_ms,
        context_chars=result.context_chars,
        corpus_version=result.corpus_version,
        lexical_candidates=result.lexical_candidates,
        semantic_candidates=result.semantic_candidates,
    )


def observe_evidence(usage: AiUsage, evidence: Evidence, query_type: QueryType) -> None:
    """Attach privacy-safe retrieval facts to the operation that requested them."""
    usage.observe_retrieval(
        query_type=query_type.value,
        evidence_count=len(evidence.citations),
        latency_ms=evidence.latency_ms,
        semantic_available=evidence.semantic_available,
        corpus_version=evidence.corpus_version or None,
        lexical_candidates=evidence.lexical_candidates,
        semantic_candidates=evidence.semantic_candidates,
        context_chars=evidence.context_chars,
    )


# -- catalogue helpers -----------------------------------------------------------------------


def _entries() -> list[CatalogueEntry]:
    return build_catalogue().messages


def message_key(entry: CatalogueEntry) -> str:
    release = entry.release or entry.version or ""
    return f"{entry.format.value}:{entry.message_type}:{entry.lane.value}:{release}"


def _tokens(text: str) -> list[str]:
    return [token for token in TOKEN.findall(text.lower()) if token not in STOP]


def lexical_candidates(
    request: str, entries: list[CatalogueEntry], *, limit: int = 5
) -> list[tuple[CatalogueEntry, float, str]]:
    """Deterministic catalogue ranking: token overlap with name, description, type, area."""
    tokens = _tokens(request)
    if not tokens:
        return []
    scored: list[tuple[CatalogueEntry, float, str]] = []
    for entry in entries:
        haystack = " ".join(
            [
                entry.message_type,
                entry.version or "",
                entry.name,
                entry.short_description,
                entry.business_area_label,
                entry.capability_summary,
            ]
        ).lower()
        words = set(_tokens(haystack))
        score = 0.0
        reasons: list[str] = []
        for token in tokens:
            if token == entry.message_type.lower() or token == (entry.version or "").lower():
                score += 6
                reasons.append(f"names {entry.message_type}")
            elif token in words:
                score += 1.5 if token in entry.name.lower() else 1.0
                reasons.append(token)
        if score <= 0:
            continue
        name_tokens = set(_tokens(entry.name))
        if name_tokens and name_tokens <= set(tokens):
            # Every word of the message's name is in the request: "receive against payment"
            # is the instruction, not its confirmation, however many words they share.
            score += 2.0
        score -= 0.3 * len(name_tokens - set(tokens))
        if entry.lane is Lane.CONFIGURED:
            score += 0.5  # a reviewed configuration is the better default
        if entry.generatable:
            score += 0.25
        scored.append((entry, score, ", ".join(dict.fromkeys(reasons))[:200]))
    scored.sort(
        key=lambda item: (
            -item[1],
            item[0].format.value,
            item[0].message_type,
            message_key(item[0]),
        )
    )
    return scored[:limit]


# -- identification --------------------------------------------------------------------------


def identify(
    request: str, *, format_: MessageFormat | None = None, limit: int = 5
) -> dict[str, Any]:
    started = time.monotonic()
    entries = [e for e in _entries() if format_ is None or e.format is format_]
    evidence = gather_evidence(
        request,
        query_type=QueryType.MESSAGE_SELECTION,
        format_=format_,
        message_type=None,
        release=None,
    )
    # Messages the evidence points at get a boost; the catalogue stays the only source of truth.
    evidence_types = Counter(
        (item.format.value, item.message_type or "")
        for item in evidence.citations
        if item.message_type
    )
    ranked = lexical_candidates(request, entries, limit=limit * 2)
    boosted: list[tuple[CatalogueEntry, float, str]] = []
    seen: set[str] = set()
    for entry, score, reason in ranked:
        # Evidence nudges, never decides: a message with a long indexed guide would otherwise
        # outrank a better-named message that simply has no document yet.
        boost = min(evidence_types.get((entry.format.value, entry.message_type), 0), 2)
        boosted.append((entry, score + boost * 0.5, reason))
        seen.add(message_key(entry))
    for (fmt, mt), count in evidence_types.most_common(limit):
        for entry in entries:
            if (
                entry.format.value == fmt
                and entry.message_type == mt
                and message_key(entry) not in seen
            ):
                boosted.append((entry, count * 0.5, "named in indexed sources"))
                seen.add(message_key(entry))
    boosted.sort(key=lambda item: (-item[1], message_key(item[0])))
    candidates = boosted[:limit]
    by_key = {message_key(entry): entry for entry, _s, _r in candidates}
    total = sum(score for _e, score, _r in candidates) or 1.0
    seed = {
        "candidates": [
            {
                "messageKey": message_key(entry),
                "confidence": round(min(0.95, score / total), 3),
                "reason": reason or "catalogue match",
            }
            for entry, score, reason in candidates
        ],
        "explanation": (
            f"Best catalogue match: {candidates[0][0].message_type} — {candidates[0][0].name}."
            if candidates
            else "No catalogue entry matches the request."
        ),
        "missingInformation": [],
        "confidence": round(min(0.95, candidates[0][1] / total), 3) if candidates else 0.0,
    }
    usage = AiUsage()
    usage.set_context(None, None, format_.value if format_ else None)
    observe_evidence(usage, evidence, QueryType.MESSAGE_SELECTION)
    payload = seed
    if candidates and authoring_provider.available:
        try:
            payload = authoring_provider.complete(
                role="IDENTIFY",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        "Task: choose the financial message(s) that fit the request. Only the "
                        "listed candidate keys exist; never propose another.",
                        "Candidates:\n"
                        + "\n".join(
                            f"- {message_key(e)} | {e.name} | {e.short_description[:160]}"
                            for e, _s, _r in candidates
                        ),
                        fence_user(request),
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(seed),
                    ]
                ),
                schema_name="identify",
                json_schema=identify_schema(list(by_key)),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
            usage.provider = "deterministic"
    chosen: list[dict[str, Any]] = []
    raw_candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    for item in raw_candidates if isinstance(raw_candidates, list) else []:
        if not isinstance(item, dict):
            continue
        found = by_key.get(str(item.get("messageKey")))
        if found is None:
            continue  # an invented key is dropped, never surfaced
        chosen.append(
            {
                "format": found.format.value,
                "messageType": found.message_type,
                "version": found.version,
                "release": found.release,
                "lane": found.lane.value,
                "name": found.name,
                "readiness": found.readiness.value,
                "readinessLabel": found.readiness_label,
                "generatable": found.generatable,
                "confidence": float(item.get("confidence", 0) or 0),
                "reason": str(item.get("reason", ""))[:400],
            }
        )
    _metric("IDENTIFY", usage, started, "OK" if chosen else "NO_MATCH")
    missing_raw = payload.get("missingInformation", []) if isinstance(payload, dict) else []
    confidence_raw = payload.get("confidence", 0) if isinstance(payload, dict) else 0
    return {
        "request": request[:2000],
        "candidates": chosen,
        "explanation": str(payload.get("explanation", seed["explanation"]))[:800]
        if isinstance(payload, dict)
        else seed["explanation"],
        "missingInformation": [
            str(x)[:200] for x in (missing_raw if isinstance(missing_raw, list) else [])
        ][:10],
        "confidence": float(confidence_raw) if isinstance(confidence_raw, int | float) else 0.0,
        "retrievalEvidence": evidence.as_dict(),
        "aiUsage": usage.as_dict(),
        "deterministicCandidates": [
            {"messageKey": message_key(e), "score": s, "reason": r} for e, s, r in candidates
        ],
    }


# -- structure + values ------------------------------------------------------------------------


def _field_index(spec: MessageSpec) -> dict[str, SpecField]:
    return {item.id: item for item in spec.fields}


def _structure_rows(spec: MessageSpec) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "presence": item.presence.value,
            "label": item.display_name,
            "format": item.format_explanation[:60],
            "codes": item.allowed_codes,
        }
        for item in sorted(spec.fields, key=lambda entry: entry.order)
    ]


@dataclass
class ValueCheck:
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)


def check_values(spec: MessageSpec, values: list[dict[str, Any]]) -> ValueCheck:
    """The deterministic boundary between the model and the engine.

    Unknown field → rejected. Unknown code → rejected. Value that looks like raw FIN or XML
    → rejected. The rest proceeds to the ordinary validator, which has the final word.
    """
    index = _field_index(spec)
    check = ValueCheck()
    for item in values:
        field_id = str(item.get("fieldId", ""))
        value = str(item.get("value", "")).strip()
        occurrence = int(item.get("occurrence", 1) or 1)
        spec_field = index.get(field_id)
        if spec_field is None:
            check.rejected.append(
                {"fieldId": field_id, "code": "AI_UNKNOWN_FIELD", "value": value[:40]}
            )
            continue
        if not value:
            check.rejected.append({"fieldId": field_id, "code": "AI_EMPTY_VALUE"})
            continue
        if (
            value.startswith(("{1:", "{2:", "{4:", ":16R:"))
            or value.lstrip().startswith("<?xml")
            or "</" in value
        ):
            check.rejected.append({"fieldId": field_id, "code": "AI_RAW_MESSAGE_REJECTED"})
            continue
        if (
            spec_field.allowed_codes
            and spec_field.input_kind.value == "SELECT"
            and value not in spec_field.allowed_codes
        ):
            check.rejected.append(
                {
                    "fieldId": field_id,
                    "code": "AI_INVALID_CODE",
                    "value": value[:40],
                    "allowed": spec_field.allowed_codes[:12],
                }
            )
            continue
        check.accepted.append(
            {"fieldId": field_id, "occurrence": max(1, min(100, occurrence)), "value": value[:2000]}
        )
    return check


def _to_inputs(
    spec: MessageSpec, values: list[dict[str, Any]]
) -> tuple[list[FieldInput], list[ElementInput]]:
    if spec.format is MessageFormat.MT:
        return [
            FieldInput(id=v["fieldId"], occurrence=v["occurrence"], value=v["value"])
            for v in values
        ], []
    return [], [
        ElementInput(path=v["fieldId"], occurrence=v["occurrence"], value=v["value"])
        for v in values
    ]


def _generate(
    spec: MessageSpec,
    values: list[dict[str, Any]],
    *,
    profile_id: str,
    persist: bool = False,
    output_modes: list[OutputMode] | None = None,
    scenario_id: str | None = None,
) -> GenerateResult:
    fields, elements = _to_inputs(spec, values)
    request = GenerateRequest(
        format=spec.format,
        message_type=spec.version or spec.message_type
        if spec.format is MessageFormat.MX
        else spec.message_type,
        profile_id=profile_id,
        scenario_id=scenario_id,
        fields=fields,
        elements=elements,
        output_modes=output_modes,
        persist=persist,
        lane=spec.lane,
        release=spec.release if spec.format is MessageFormat.MT else None,
    )
    return studio_service.generate(request, source="AI_AUTHORING")


def resolve_spec(
    format_: MessageFormat, message_type: str, *, lane: Lane, release: str | None
) -> MessageSpec:
    try:
        return message_spec(format_, message_type, lane, release)
    except LookupError as error:
        code = getattr(error, "code", "MESSAGE_GENERATION_NOT_READY")
        raise AuthoringError(
            code, str(error), status=404, blockers=list(getattr(error, "blockers", ()))
        ) from error
    except KeyError as error:
        raise AuthoringError(
            "STRUCTURE_SOURCE_MISSING", str(error).strip("'\""), status=404
        ) from error


def _seed_values(spec: MessageSpec, variant: SampleVariant) -> list[dict[str, Any]]:
    sample = build_sample(
        spec.format,
        spec.version or spec.message_type if spec.format is MessageFormat.MX else spec.message_type,
        variant,
        spec.lane,
        spec.release if spec.format is MessageFormat.MT else None,
    )
    if spec.format is MessageFormat.MT:
        return [
            {"fieldId": i.id, "occurrence": i.occurrence, "value": i.value}
            for i in sample.inputs
            if i.id
        ]
    return [
        {"fieldId": e.path, "occurrence": e.occurrence, "value": e.value} for e in sample.elements
    ]


def _variant_for(spec: MessageSpec, sample_type: str) -> SampleVariant:
    wanted = SampleVariant(sample_type.upper())
    variants = available_variants(
        spec.format,
        spec.version or spec.message_type if spec.format is MessageFormat.MX else spec.message_type,
        spec.lane,
        spec.release if spec.format is MessageFormat.MT else None,
    )
    if wanted in variants:
        return wanted
    if wanted is SampleVariant.TYPICAL and SampleVariant.MINIMAL in variants:
        return SampleVariant.MINIMAL
    return variants[0] if variants else SampleVariant.MINIMAL


# -- prepare -----------------------------------------------------------------------------------


def prepare(
    scenario: str,
    *,
    format_: MessageFormat | None,
    message_type: str | None,
    release: str | None,
    lane: Lane,
    known_values: list[dict[str, Any]] | None,
    profile_id: str,
) -> dict[str, Any]:
    started = time.monotonic()
    identification: dict[str, Any] | None = None
    if not message_type:
        identification = identify(scenario, format_=format_)
        if not identification["candidates"]:
            raise AuthoringError(
                "RAG_NO_RELEVANT_EVIDENCE",
                "No discovered message matches the request.",
                status=404,
                identification=identification,
            )
        top = identification["candidates"][0]
        format_ = MessageFormat(top["format"])
        message_type = str(top["version"] or top["messageType"])
        lane = Lane(top["lane"])
        release = top["release"] if format_ is MessageFormat.MT else None
    if format_ is None:
        format_ = MessageFormat.MT if message_type.upper().startswith("MT") else MessageFormat.MX
    spec = resolve_spec(format_, message_type, lane=lane, release=release)
    seed_values = _seed_values(
        spec,
        SampleVariant.TYPICAL
        if SampleVariant.TYPICAL
        in available_variants(
            spec.format,
            spec.version or spec.message_type
            if spec.format is MessageFormat.MX
            else spec.message_type,
            spec.lane,
            spec.release if spec.format is MessageFormat.MT else None,
        )
        else SampleVariant.MINIMAL,
    )
    known = check_values(spec, known_values or [])
    merged = {(v["fieldId"], v["occurrence"]): v for v in seed_values}
    for v in known.accepted:
        merged[(v["fieldId"], v["occurrence"])] = v
    seed = {
        "scenario": scenario[:600],
        "values": list(merged.values()),
        "missingFields": [],
        "notes": ["Seed values are deterministic synthetic values; the request may refine them."],
        "questions": [],
    }
    evidence = gather_evidence(
        scenario,
        query_type=QueryType.SAMPLE_PREPARATION,
        format_=spec.format,
        message_type=spec.version or spec.message_type,
        release=spec.release,
    )
    usage = AiUsage()
    usage.set_context(spec.message_type, spec.release or spec.version, spec.format.value)
    observe_evidence(usage, evidence, QueryType.SAMPLE_PREPARATION)
    payload: dict[str, Any] = seed
    if authoring_provider.available:
        try:
            payload = authoring_provider.complete(
                role="PREPARE",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        f"Task: prepare canonical values for {spec.message_type}"
                        + (f" {spec.release}" if spec.release else "")
                        + f" ({spec.lane.value}). Keep the message type and release. "
                        "Use only the allowed field ids. "
                        "Where the request gives a business value, place it; "
                        "where it is silent, keep the seed value or list the field under "
                        "missingFields and ask one question.",
                        structure_block(_structure_rows(spec)),
                        fence_user(scenario),
                        "Known values supplied by the caller (already validated): "
                        + json.dumps(known.accepted),
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(seed),
                    ]
                ),
                schema_name="prepare",
                json_schema=canonical_values_schema([f.id for f in spec.fields]),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
    check = check_values(spec, list(payload.get("values", [])))
    for v in known.accepted:  # caller-supplied values are never overwritten by the model
        check.accepted = [
            a
            for a in check.accepted
            if (a["fieldId"], a["occurrence"]) != (v["fieldId"], v["occurrence"])
        ]
        check.accepted.append(v)
    validation = _generate(spec, check.accepted, profile_id=profile_id)
    _metric("PREPARE", usage, started, "OK" if validation.valid else "NEEDS_INPUT")
    return {
        "format": spec.format.value,
        "messageType": spec.message_type,
        "version": spec.version,
        "release": spec.release,
        "lane": spec.lane.value,
        "scenario": str(payload.get("scenario", scenario))[:600],
        "canonicalValues": check.accepted,
        "rejectedValues": check.rejected,
        "missingFields": [m for m in payload.get("missingFields", []) if m in _field_index(spec)][
            :50
        ],
        "questions": [str(q)[:300] for q in payload.get("questions", [])][:10],
        "notes": [str(n)[:300] for n in payload.get("notes", [])][:10],
        "validation": validation.validation.model_dump(mode="json", by_alias=True),
        "valid": validation.valid,
        "capability": {
            "readiness": "GENERATION_READY",
            "lane": spec.lane.value,
            "capabilityStatement": spec.capability_statement,
            "structureSource": spec.structure_source,
        },
        "identification": identification,
        "retrievalEvidence": evidence.as_dict(),
        "aiUsage": usage.as_dict(),
    }


# -- AI sample --------------------------------------------------------------------------------


def sample_cache_key(
    spec: MessageSpec, sample_type: str, profile_id: str, provider_name: str, model: str
) -> str:
    from app.rule_engine.registry import rule_pack_registry

    packs = sorted(
        pack.pack_id
        for pack in rule_pack_registry.packs()
        if pack.pack.format is spec.format and pack.pack.message_type == spec.message_type
    )
    structure_checksum = _structure_checksum(spec)
    corpus = knowledge_service.message_corpus_version(
        spec.format.value,
        spec.message_type,
        spec.release if spec.format is MessageFormat.MT else spec.version,
    )
    raw = "|".join(
        [
            spec.format.value,
            spec.message_type,
            spec.release or spec.version or "",
            spec.lane.value,
            sample_type.upper(),
            profile_id,
            structure_checksum,
            ",".join(packs),
            corpus,
            PROMPT_VERSION,
            OUTPUT_SCHEMA_VERSION,
            provider_name,
            model,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _structure_checksum(spec: MessageSpec) -> str:
    digest = hashlib.sha256()
    for item in sorted(spec.fields, key=lambda f: f.id):
        digest.update(
            f"{item.id}|{item.presence.value}|{item.format_explanation}|{','.join(item.allowed_codes)}|".encode()
        )
    return digest.hexdigest()


def ai_sample(
    *,
    format_: MessageFormat,
    message_type: str,
    release: str | None,
    lane: Lane,
    sample_type: str,
    profile_id: str,
    refresh: bool,
    scenario: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    settings = get_settings()
    spec = resolve_spec(format_, message_type, lane=lane, release=release)
    variant = _variant_for(spec, sample_type)
    provider_name = authoring_provider.name
    model = settings.ai_chat_deployment or settings.openrouter_primary_model
    key = sample_cache_key(spec, variant.value, profile_id, provider_name, model) + (
        hashlib.sha256(scenario.encode()).hexdigest()[:16] if scenario else ""
    )
    usage = AiUsage(provider=provider_name, model=model)
    usage.set_context(spec.message_type, spec.release or spec.version, spec.format.value)
    cached = None if refresh else knowledge_service.sample_cache_get(key)
    if cached is not None:
        usage.cache_hit = True
        usage.calls_avoided = int(cached.get("llmCalls", 0))
        usage.tokens_avoided = int(cached.get("promptTokens", 0)) + int(
            cached.get("completionTokens", 0)
        )
        values = list(cached["canonicalValues"])
        result = _generate(spec, values, profile_id=profile_id)
        _metric("SAMPLE", usage, started, "CACHE_HIT")
        return _sample_response(
            spec,
            variant,
            values,
            result,
            cached.get("retrievalEvidence", {}),
            usage,
            cache_status="HIT",
            attempts=0,
            repair_log=[],
            outcome=str(cached.get("outcome") or "CACHE"),
            # The proof travels with the cached values: the round trip was run when the
            # sample was first validated, and the structure checksum is part of the key.
            round_trip=cached.get("roundTrip"),
        )

    seed_values = _seed_values(spec, variant)
    evidence = gather_evidence(
        scenario
        or (
            f"{spec.message_type} {variant.value.lower()} sample: mandatory fields, "
            "typical optional structures, codes"
        ),
        query_type=QueryType.SAMPLE_PREPARATION,
        format_=spec.format,
        message_type=spec.version or spec.message_type,
        release=spec.release,
    )
    observe_evidence(usage, evidence, QueryType.SAMPLE_PREPARATION)
    seed = {
        "scenario": scenario or f"{variant.value.title()} synthetic {spec.message_type} sample",
        "values": seed_values,
        "missingFields": [],
        "notes": [],
    }
    values = seed_values
    attempts = 0
    repair_log: list[dict[str, Any]] = []
    outcome = "DETERMINISTIC_FALLBACK"
    result = _generate(spec, values, profile_id=profile_id)
    if authoring_provider.available:
        max_attempts = max(1, settings.knowledge_ai_max_repair_attempts)
        findings: list[dict[str, Any]] = []
        candidate_values = seed_values
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                payload = authoring_provider.complete(
                    role="SAMPLE" if attempt == 1 else "SAMPLE_REPAIR",
                    system_prompt=BOUNDARY,
                    user_content="\n\n".join(
                        [
                            f"Task: produce a coherent {variant.value.lower()} synthetic sample "
                            "for "
                            f"{spec.message_type}{' ' + spec.release if spec.release else ''} "
                            f"({spec.lane.value}). "
                            "Decide the business scenario and which optional structures belong; "
                            "keep values structurally valid. "
                            "References, dates, amounts and identifiers stay synthetic.",
                            structure_block(_structure_rows(spec)),
                            fence_user(scenario) if scenario else "",
                            "Evidence:\n" + evidence.prompt(),
                            seed_block(seed),
                            (
                                "Deterministic validation findings on your previous answer "
                                "(fix exactly these):\n" + json.dumps(findings)
                            )
                            if findings
                            else "",
                        ]
                    ),
                    schema_name="sample",
                    json_schema=canonical_values_schema(
                        [f.id for f in spec.fields], allow_questions=False
                    ),
                    usage=usage,
                )
            except AiUnavailable as error:
                repair_log.append({"attempt": attempt, "outcome": error.code})
                break
            check = check_values(spec, list(payload.get("values", [])))
            candidate_values = check.accepted
            candidate = _generate(spec, candidate_values, profile_id=profile_id)
            findings = [
                {
                    "ruleId": i.rule_id,
                    "field": i.field,
                    "location": i.location,
                    "message": i.message,
                    "expected": i.expected,
                    "current": i.current_value,
                    "suggestion": i.suggestion,
                }
                for i in candidate.validation.errors[:20]
            ] + [{"ruleId": r["code"], "field": r["fieldId"]} for r in check.rejected[:20]]
            repair_log.append(
                {
                    "attempt": attempt,
                    "errors": len(candidate.validation.errors),
                    "rejected": len(check.rejected),
                }
            )
            if candidate.valid and not check.rejected:
                values, result, outcome = candidate_values, candidate, "AI_VALID"
                break
        else:
            outcome = "AI_REPAIR_EXHAUSTED"
        if outcome == "AI_REPAIR_EXHAUSTED" and not result.valid:
            _metric("SAMPLE", usage, started, "AI_SAMPLE_GENERATION_FAILED")
            raise AuthoringError(
                "AI_SAMPLE_GENERATION_FAILED",
                f"no valid sample after {attempts} attempt(s)",
                status=422,
                findings=findings,
                repairLog=repair_log,
                aiUsage=usage.as_dict(),
            )
    if not result.valid:
        _metric("SAMPLE", usage, started, "AI_SAMPLE_GENERATION_FAILED")
        raise AuthoringError(
            "AI_SAMPLE_GENERATION_FAILED",
            "the deterministic seed did not validate; the structure pack needs review",
            status=422,
            findings=[
                i.model_dump(mode="json", by_alias=True) for i in result.validation.errors[:20]
            ],
        )
    round_trip = _round_trip(spec, result)
    knowledge_service.sample_cache_put(
        key,
        format_=spec.format.value,
        message_type=spec.message_type,
        release=spec.release or spec.version or "",
        lane=spec.lane.value,
        sample_type=variant.value,
        payload={
            "canonicalValues": values,
            "retrievalEvidence": evidence.as_dict(),
            "llmCalls": usage.llm_calls,
            "promptTokens": usage.prompt_tokens,
            "completionTokens": usage.completion_tokens,
            "outcome": outcome,
            "roundTrip": round_trip,
        },
        provider=usage.provider,
        model=usage.model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        llm_calls=usage.llm_calls,
    )
    _metric("SAMPLE", usage, started, outcome)
    return _sample_response(
        spec,
        variant,
        values,
        result,
        evidence.as_dict(),
        usage,
        cache_status="MISS",
        attempts=attempts,
        repair_log=repair_log,
        outcome=outcome,
        round_trip=round_trip,
    )


def _round_trip(spec: MessageSpec, result: GenerateResult) -> dict[str, Any]:
    """Compose → parse → compose, through the ordinary parsers. Recorded, never assumed."""
    try:
        if spec.format is MessageFormat.MT:
            from app.studio.mt.parser import parse_message as parse_mt

            text = result.outputs.block4 or ""
            if spec.lane is Lane.KNOWLEDGE_PREVIEW:
                from app.knowledge_base.preview import preview_registries

                parsed = parse_mt(
                    text,
                    specification=preview_registries().resolve_mt(spec.message_type, spec.release),
                )
            else:
                parsed = parse_mt(text, message_type=spec.message_type)
            again = studio_service.generate(
                GenerateRequest(
                    format=MessageFormat.MT,
                    message_type=spec.message_type,
                    fields=parsed.fields,
                    persist=False,
                    lane=spec.lane,
                    release=spec.release,
                    output_modes=[OutputMode.BLOCK4],
                ),
                source="AI_AUTHORING",
            )
            return {
                "performed": True,
                "identical": again.outputs.block4 == text and not parsed.errors,
                "importIssues": len(parsed.errors),
            }
        from app.studio.mx.parser import parse_message as parse_mx

        xml = result.outputs.xml or result.outputs.document or ""
        registry = None
        if spec.lane is Lane.KNOWLEDGE_PREVIEW:
            from app.knowledge_base.preview import preview_registries

            registry = preview_registries().mx_registry
        parsed_mx = parse_mx(xml, registry)
        again = studio_service.generate(
            GenerateRequest(
                format=MessageFormat.MX,
                message_type=spec.version or spec.message_type,
                elements=parsed_mx.elements,
                persist=False,
                lane=spec.lane,
                output_modes=[OutputMode.DOCUMENT],
            ),
            source="AI_AUTHORING",
        )
        return {
            "performed": True,
            "identical": again.outputs.document == result.outputs.document and not parsed_mx.errors,
            "importIssues": len(parsed_mx.errors),
        }
    except Exception as error:  # noqa: BLE001 - a failed round trip is reported, not raised
        return {"performed": True, "identical": False, "error": type(error).__name__}


def _sample_response(
    spec: MessageSpec,
    variant: SampleVariant,
    values: list[dict[str, Any]],
    result: GenerateResult,
    evidence: dict[str, Any],
    usage: AiUsage,
    *,
    cache_status: str,
    attempts: int,
    repair_log: list[dict[str, Any]],
    outcome: str = "CACHE",
    round_trip: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields, elements = _to_inputs(spec, values)
    return {
        "sampleId": (
            f"{spec.message_type}-{spec.release or spec.version or 'CONFIGURED'}-{variant.value}-AI"
        ),
        "format": spec.format.value,
        "messageType": spec.message_type,
        "version": spec.version,
        "release": spec.release,
        "lane": spec.lane.value,
        "sampleType": variant.value,
        "title": f"AI {variant.value.title()} sample",
        "description": "AI-generated synthetic sample, validated by the deterministic engine.",
        "canonicalValues": values,
        "inputs": [f.model_dump(mode="json", by_alias=True) for f in fields],
        "elements": [e.model_dump(mode="json", by_alias=True) for e in elements],
        "validation": result.validation.model_dump(mode="json", by_alias=True),
        "valid": result.valid,
        "outputs": result.outputs.model_dump(mode="json", by_alias=True),
        "checksum": result.checksum,
        "provenance": result.provenance.model_dump(mode="json", by_alias=True)
        if result.provenance
        else None,
        "capability": {
            "readiness": "GENERATION_READY",
            "lane": spec.lane.value,
            "capabilityStatement": spec.capability_statement,
            "structureSource": spec.structure_source,
        },
        "cache": {
            "status": cache_status,
            "llmCallsAvoided": usage.calls_avoided,
            "tokensAvoided": usage.tokens_avoided,
        },
        "aiUsage": usage.as_dict(),
        "retrievalEvidence": evidence,
        "repair": {"attempts": attempts, "log": repair_log, "outcome": outcome},
        "roundTrip": round_trip,
        "synthetic": True,
    }


# -- bulk test data ----------------------------------------------------------------------------


def test_data(
    *,
    format_: MessageFormat,
    message_type: str,
    release: str | None,
    lane: Lane,
    scenario: str,
    count: int,
    sample_type: str,
    test_intent: str,
    profile_id: str,
    reviewer_mode: bool,
    output_modes: list[OutputMode] | None,
) -> dict[str, Any]:
    started = time.monotonic()
    settings = get_settings()
    count = max(1, min(count, settings.knowledge_ai_max_batch))
    spec = resolve_spec(format_, message_type, lane=lane, release=release)
    variant = _variant_for(spec, sample_type)
    base = _seed_values(spec, variant)
    evidence = gather_evidence(
        scenario,
        query_type=QueryType.TEST_SCENARIO_PREPARATION,
        format_=spec.format,
        message_type=spec.version or spec.message_type,
        release=spec.release,
    )
    usage = AiUsage(provider=authoring_provider.name)
    usage.set_context(spec.message_type, spec.release or spec.version, spec.format.value)
    observe_evidence(usage, evidence, QueryType.TEST_SCENARIO_PREPARATION)
    if test_intent.upper() == "NEGATIVE":
        return _negative(
            spec,
            base,
            scenario,
            count,
            profile_id,
            reviewer_mode,
            evidence,
            usage,
            started,
            output_modes,
        )
    seed = {
        "scenarios": [
            {"title": f"Scenario {index}", "values": _vary(base, index)}
            for index in range(1, count + 1)
        ]
    }
    payload: dict[str, Any] = seed
    if authoring_provider.available:
        try:
            payload = authoring_provider.complete(
                role="TEST_DATA",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        f"Task: "
                        f"produce {count} distinct synthetic test scenarios for {spec.message_type}"
                        + (f" {spec.release}" if spec.release else "")
                        + ". "
                        "Vary business content (references, amounts, dates, optional "
                        "structures) while keeping every value structurally valid.",
                        structure_block(_structure_rows(spec)),
                        fence_user(scenario),
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(seed),
                    ]
                ),
                schema_name="scenarios",
                json_schema=scenarios_schema([f.id for f in spec.fields], count=count),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
    scenarios_out: list[dict[str, Any]] = []
    generated = 0
    for index, item in enumerate(list(payload.get("scenarios", []))[:count], start=1):
        check = check_values(spec, list(item.get("values", [])))
        values = check.accepted or _vary(base, index)
        result = _generate(
            spec,
            values,
            profile_id=profile_id,
            output_modes=output_modes,
            scenario_id=f"AI-{index:03d}",
        )
        if not result.valid:
            # One repair against the deterministic findings: fall back to the seed variant.
            values = _vary(base, index)
            result = _generate(
                spec,
                values,
                profile_id=profile_id,
                output_modes=output_modes,
                scenario_id=f"AI-{index:03d}",
            )
        generated += 1 if result.valid else 0
        scenarios_out.append(
            {
                "scenarioId": f"AI-{index:03d}",
                "title": str(item.get("title", f"Scenario {index}"))[:200],
                "canonicalValues": values,
                "rejectedValues": check.rejected,
                "validation": result.validation.model_dump(mode="json", by_alias=True),
                "valid": result.valid,
                "outputs": result.outputs.model_dump(mode="json", by_alias=True),
                "checksum": result.checksum,
            }
        )
    _metric("TEST_DATA", usage, started, f"{generated}/{count}")
    return _test_data_response(spec, scenarios_out, evidence, usage, "POSITIVE", generated)


def _vary(base: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    """Deterministic per-scenario variation of references and amounts — enough to make
    scenarios distinct without a model, and the fallback when the model's answer fails."""
    varied: list[dict[str, Any]] = []
    for item in base:
        value = str(item["value"])
        field_id = str(item["fieldId"]).upper()
        if re.fullmatch(r"[A-Z0-9]{6,16}", value) and (
            "20C" in field_id
            or "-20-" in field_id
            or "-21-" in field_id
            or "REF" in field_id
            or "ID" in field_id
        ):
            value = (value[: max(0, 16 - 3)] + f"{index:03d}")[:16]
        elif re.fullmatch(r"[A-Z]{3}\d+,\d*", value):
            currency, amount = value[:3], value[3:]
            whole = amount.split(",")[0]
            fraction = amount.split(",")[1] if "," in amount else ""
            value = f"{currency}{int(whole) + index * 100},{fraction}"
        elif re.fullmatch(r"\d+\.\d+", value):
            value = f"{float(value) + index:.2f}"
        varied.append({**item, "value": value})
    return varied


def _negative(
    spec: MessageSpec,
    base: list[dict[str, Any]],
    scenario: str,
    count: int,
    profile_id: str,
    reviewer_mode: bool,
    evidence: Evidence,
    usage: AiUsage,
    started: float,
    output_modes: list[OutputMode] | None,
) -> dict[str, Any]:
    from app.rule_engine.registry import rule_pack_registry

    effective = rule_pack_registry.effective(spec.format, spec.message_type, profile_id)
    rules = [(rule.rule.rule_id, rule.rule.title) for rule in getattr(effective, "rules", [])]
    if not rules:
        _metric("TEST_DATA_NEGATIVE", usage, started, "NO_ACTIVE_RULES")
        return _test_data_response(
            spec,
            [],
            evidence,
            usage,
            "NEGATIVE",
            0,
            note=(
                "No reviewed active Rule Pack applies to this message, so no negative "
                "scenario can be proven. "
                + (
                    "Candidate (REVIEW_REQUIRED) rules are not used outside reviewer mode."
                    if not reviewer_mode
                    else "Reviewer mode is on, but no candidate rule is installed for "
                    "runtime evaluation either."
                )
            ),
        )
    rule_ids = [rule_id for rule_id, _title in rules]
    seed = {
        "mutations": [
            {
                "expectedRuleId": rule_ids[i % len(rule_ids)],
                "title": f"Violate {rule_ids[i % len(rule_ids)]}",
                "values": base,
            }
            for i in range(min(count, len(rule_ids)))
        ]
    }
    payload: dict[str, Any] = seed
    if authoring_provider.available:
        try:
            payload = authoring_provider.complete(
                role="TEST_DATA_NEGATIVE",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        f"Task: "
                        "for each listed active rule, propose canonical values for "
                        f"{spec.message_type} that violate exactly that rule and nothing else. "
                        f"The deterministic validator will decide whether the rule actually fails.",
                        "Active rules (id | title):\n"
                        + "\n".join(f"- {rid} | {title}" for rid, title in rules),
                        structure_block(_structure_rows(spec)),
                        fence_user(scenario),
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(seed),
                    ]
                ),
                schema_name="negative",
                json_schema=negative_schema([f.id for f in spec.fields], rule_ids),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
    scenarios_out: list[dict[str, Any]] = []
    proven = 0
    for index, item in enumerate(list(payload.get("mutations", []))[:count], start=1):
        expected = str(item.get("expectedRuleId", ""))
        check = check_values(spec, list(item.get("values", [])))
        result = _generate(
            spec,
            check.accepted,
            profile_id=profile_id,
            output_modes=output_modes,
            scenario_id=f"NEG-{index:03d}",
        )
        actual = [i.rule_id for i in result.validation.errors]
        proved = expected in actual
        proven += 1 if proved else 0
        scenarios_out.append(
            {
                "scenarioId": f"NEG-{index:03d}",
                "title": str(item.get("title", ""))[:200],
                "expectedRuleId": expected,
                "actualFindings": actual,
                "proven": proved,
                "status": "NEGATIVE_PROVEN" if proved else "NEGATIVE_NOT_PROVEN",
                "canonicalValues": check.accepted,
                "rejectedValues": check.rejected,
                "validation": result.validation.model_dump(mode="json", by_alias=True),
                "outputs": result.outputs.model_dump(mode="json", by_alias=True),
                "checksum": result.checksum,
            }
        )
    _metric("TEST_DATA_NEGATIVE", usage, started, f"{proven}/{len(scenarios_out)}")
    return _test_data_response(spec, scenarios_out, evidence, usage, "NEGATIVE", proven)


def _test_data_response(
    spec: MessageSpec,
    scenarios: list[dict[str, Any]],
    evidence: Evidence,
    usage: AiUsage,
    intent: str,
    generated: int,
    note: str | None = None,
) -> dict[str, Any]:
    import uuid

    return {
        "requestId": uuid.uuid4().hex,
        "format": spec.format.value,
        "messageType": spec.message_type,
        "version": spec.version,
        "release": spec.release,
        "lane": spec.lane.value,
        "testIntent": intent,
        "capability": {
            "readiness": "GENERATION_READY",
            "lane": spec.lane.value,
            "capabilityStatement": spec.capability_statement,
            "structureSource": spec.structure_source,
        },
        "scenarios": scenarios,
        "generated": generated,
        "total": len(scenarios),
        "retrievalEvidence": evidence.as_dict(),
        "aiUsage": usage.as_dict(),
        "cache": {"status": "MISS"},
        "note": note,
        "synthetic": True,
    }


# -- presentation enrichment ---------------------------------------------------------------------


def enrich_presentation(
    *, format_: MessageFormat, message_type: str, release: str | None, lane: Lane, field_id: str
) -> dict[str, Any]:
    started = time.monotonic()
    spec = resolve_spec(format_, message_type, lane=lane, release=release)
    target = _field_index(spec).get(field_id)
    if target is None:
        raise AuthoringError(
            "AI_UNKNOWN_FIELD", f"{field_id} is not a field of {spec.message_type}", status=404
        )
    key = hashlib.sha256(
        "|".join(
            [
                spec.format.value,
                spec.message_type,
                str(spec.release or spec.version),
                field_id,
                PROMPT_VERSION,
                knowledge_service.message_corpus_version(
                    spec.format.value, spec.message_type, spec.release or spec.version
                ),
            ]
        ).encode()
    ).hexdigest()
    cached = knowledge_service.presentation_get(key)
    deterministic = {
        "displayLabel": target.display_name[:80],
        "businessMeaning": target.business_meaning
        or target.technical_meaning
        or f"{target.tag or target.xpath}: {target.format_explanation}",
        "businessQuestion": target.business_question
        or f"What value should {target.display_name} carry?",
        "example": (target.examples[0].value if target.examples else ""),
        "whyNeeded": target.why_used
        or (
            "Required by the message structure."
            if target.presence is Presence.MANDATORY
            else "Optional in this message."
        ),
        "commonMistake": target.common_mistakes[0] if target.common_mistakes else "",
        "citations": [],
    }
    if cached is not None:
        usage = AiUsage(provider="cache")
        usage.set_context(spec.message_type, spec.release or spec.version, spec.format.value)
        usage.cache_hit = True
        _metric("PRESENTATION", usage, started, "CACHE_HIT")
        return {
            "fieldId": field_id,
            "presentation": cached,
            "cache": {"status": "HIT"},
            "authority": "NONE",
            "source": "AI_CACHED",
        }
    usage = AiUsage()
    usage.set_context(spec.message_type, spec.release or spec.version, spec.format.value)
    evidence = gather_evidence(
        f"{target.tag or ''} {target.qualifier or ''} {target.display_name} {target.xpath or ''}",
        query_type=QueryType.FIELD_EXPLANATION,
        format_=spec.format,
        message_type=spec.version or spec.message_type,
        release=spec.release,
    )
    observe_evidence(usage, evidence, QueryType.FIELD_EXPLANATION)
    payload = deterministic
    source = "DETERMINISTIC"
    if authoring_provider.available and evidence.citations:
        try:
            payload = authoring_provider.complete(
                role="PRESENTATION",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        f"Task: write plain-language presentation metadata for field {field_id} "
                        f"({target.tag or target.xpath}) of {spec.message_type}. "
                        f"Cite segment ids you relied on. "
                        f"This metadata has no validation authority.",
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(deterministic),
                    ]
                ),
                schema_name="presentation",
                json_schema=presentation_schema(),
                usage=usage,
            )
            source = "AI"
        except AiUnavailable:
            payload = deterministic
        known_segments = {c.segment_id for c in evidence.citations}
        payload["citations"] = [c for c in payload.get("citations", []) if c in known_segments]
        knowledge_service.presentation_put(
            key,
            format_=spec.format.value,
            message_type=spec.message_type,
            release=spec.release or spec.version or "",
            field_id=field_id,
            payload=payload,
            provider=usage.provider,
            model=usage.model,
        )
    _metric("PRESENTATION", usage, started, source)
    return {
        "fieldId": field_id,
        "presentation": payload,
        "cache": {"status": "MISS"},
        "authority": "NONE",
        "source": source,
        "retrievalEvidence": evidence.as_dict(),
        "aiUsage": usage.as_dict(),
    }


# -- cited answers and comparison -------------------------------------------------------------


def ask(
    question: str,
    *,
    format_: MessageFormat | None,
    message_type: str | None,
    release: str | None,
    query_type: QueryType = QueryType.FIELD_EXPLANATION,
) -> dict[str, Any]:
    started = time.monotonic()
    evidence = gather_evidence(
        question,
        query_type=query_type,
        format_=format_,
        message_type=message_type,
        release=release,
        limit=10,
    )
    usage = AiUsage()
    usage.set_context(message_type, release, format_.value if format_ else None)
    observe_evidence(usage, evidence, query_type)
    unsupported = {
        "answer": "The available indexed source does not establish this.",
        "supported": "UNSUPPORTED_BY_EVIDENCE",
        "citations": [],
        "caveats": ["No relevant indexed evidence was found for the question."],
    }
    if not evidence.citations:
        _metric("ASK", usage, started, "NO_EVIDENCE")
        return {
            "question": question[:2000],
            **unsupported,
            "retrievalEvidence": evidence.as_dict(),
            "aiUsage": usage.as_dict(),
        }
    seed = {
        "answer": (
            f"{len(evidence.citations)} indexed section(s) are relevant; see the citations. "
            + (
                "The source text may not be sent to the model under the current policy, "
                "so no prose summary is available."
                if not evidence.allow_text
                else ""
            )
        ).strip(),
        "supported": "PARTIAL",
        "citations": [c.segment_id for c in evidence.citations[:6]],
        "caveats": []
        if evidence.allow_text
        else ["Evidence text withheld by source policy; locations only."],
    }
    payload = seed
    if authoring_provider.available and evidence.allow_text:
        try:
            payload = authoring_provider.complete(
                role="ASK",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        "Task: answer the question from the evidence only, citing segment ids. "
                        "If the evidence does not establish the answer, say so with "
                        "supported=UNSUPPORTED_BY_EVIDENCE.",
                        fence_user(question),
                        "Evidence:\n" + evidence.prompt(),
                        seed_block(seed),
                    ]
                ),
                schema_name="answer",
                json_schema=answer_schema([c.segment_id for c in evidence.citations]),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
    known = {c.segment_id for c in evidence.citations}
    payload["citations"] = [c for c in payload.get("citations", []) if c in known]
    if not payload["citations"]:
        payload = {
            **unsupported,
            "caveats": ["The model cited nothing from the evidence; the claim is not reported."],
        }
    _metric("ASK", usage, started, str(payload.get("supported")))
    return {
        "question": question[:2000],
        **payload,
        "retrievalEvidence": evidence.as_dict(),
        "aiUsage": usage.as_dict(),
    }


def compare_releases(
    *, format_: MessageFormat, message_type: str, release_a: str, release_b: str, focus: str | None
) -> dict[str, Any]:
    started = time.monotonic()
    question = focus or f"differences in {message_type} between {release_a} and {release_b}"
    left = gather_evidence(
        question,
        query_type=QueryType.MESSAGE_COMPARISON,
        format_=format_,
        message_type=message_type,
        release=release_a,
        limit=8,
    )
    right = gather_evidence(
        question,
        query_type=QueryType.MESSAGE_COMPARISON,
        format_=format_,
        message_type=message_type,
        release=release_b,
        limit=8,
    )
    structural = _structural_diff(format_, message_type, release_a, release_b)
    usage = AiUsage()
    usage.set_context(message_type, f"{release_a}..{release_b}", format_.value)
    observe_evidence(usage, left, QueryType.MESSAGE_COMPARISON)
    observe_evidence(usage, right, QueryType.MESSAGE_COMPARISON)
    citations = left.citations + right.citations
    seed = {
        "summary": (
            f"Structural comparison of {message_type} {release_a} vs {release_b}: "
            f"{len(structural['added'])} field(s) added, {len(structural['removed'])} "
            f"removed, {len(structural['changed'])} changed."
        ),
        "differences": [
            {"area": d["area"], "change": d["change"], "citations": []}
            for d in structural["differences"][:30]
        ],
        "citations": [c.segment_id for c in citations[:10]],
    }
    payload = seed
    if authoring_provider.available and (left.allow_text or right.allow_text) and citations:
        try:
            payload = authoring_provider.complete(
                role="COMPARE",
                system_prompt=BOUNDARY,
                user_content="\n\n".join(
                    [
                        f"Task: "
                        f"summarise what changed in {message_type} between {release_a} and "
                        f"{release_b}, citing segment ids. "
                        f"Do not promote either release.",
                        f"Evidence {release_a}:\n" + left.prompt(),
                        f"Evidence {release_b}:\n" + right.prompt(),
                        "Deterministic structural comparison:\n" + json.dumps(structural)[:6000],
                        seed_block(seed),
                    ]
                ),
                schema_name="comparison",
                json_schema=comparison_schema([c.segment_id for c in citations]),
                usage=usage,
            )
        except AiUnavailable:
            payload = seed
    _metric("COMPARE", usage, started, "OK")
    return {
        "format": format_.value,
        "messageType": message_type,
        "releaseA": release_a,
        "releaseB": release_b,
        "structural": structural,
        **payload,
        "retrievalEvidence": {"releaseA": left.as_dict(), "releaseB": right.as_dict()},
        "aiUsage": usage.as_dict(),
    }


def _structural_diff(
    format_: MessageFormat, message_type: str, release_a: str, release_b: str
) -> dict[str, Any]:
    def load(release: str) -> dict[str, SpecField]:
        for lane in (Lane.KNOWLEDGE_PREVIEW, Lane.CONFIGURED):
            try:
                spec = message_spec(
                    format_,
                    message_type if format_ is MessageFormat.MT else release,
                    lane,
                    release if format_ is MessageFormat.MT else None,
                )
            except (LookupError, KeyError):
                continue
            if (spec.release or spec.version) == release or lane is Lane.CONFIGURED:
                return _field_index(spec)
        return {}

    a, b = load(release_a), load(release_b)
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(
        k
        for k in set(a) & set(b)
        if (a[k].presence, a[k].format_explanation, tuple(a[k].allowed_codes))
        != (b[k].presence, b[k].format_explanation, tuple(b[k].allowed_codes))
    )
    differences = (
        [{"area": k, "change": f"added in {release_b}"} for k in added]
        + [{"area": k, "change": f"removed in {release_b}"} for k in removed]
        + [
            {
                "area": k,
                "change": "presence/format/codes differ: "
                f"{a[k].presence.value}→{b[k].presence.value}",
            }
            for k in changed
        ]
    )
    return {
        "comparable": bool(a and b),
        "added": added,
        "removed": removed,
        "changed": changed,
        "differences": differences,
    }


def _metric(operation: str, usage: AiUsage, started: float, outcome: str) -> None:
    knowledge_service.record_ai_metric(
        request_id=usage.request_id,
        operation=operation,
        message_type=usage.message_type,
        release=usage.release,
        provider=usage.provider,
        model=usage.model,
        llm_calls=usage.llm_calls,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        cache_hit=usage.cache_hit,
        calls_avoided=usage.calls_avoided,
        tokens_avoided=usage.tokens_avoided,
        latency_ms=round((time.monotonic() - started) * 1000),
        rag_used=usage.rag_used,
        rag_mode=usage.rag_mode,
        query_type=usage.query_type,
        format_filter=usage.format_filter,
        lexical_candidates=usage.lexical_candidates,
        semantic_candidates=usage.semantic_candidates,
        evidence_count=usage.evidence_count,
        context_chars=usage.context_chars,
        retrieval_latency_ms=usage.retrieval_latency_ms,
        embedding_calls=usage.embedding_calls,
        embedding_tokens=usage.embedding_tokens,
        embedding_cache_hits=usage.embedding_cache_hits,
        embedding_latency_ms=usage.embedding_latency_ms,
        corpus_version=usage.corpus_version,
        outcome=outcome[:60],
    )


__all__ = [
    "AuthoringError",
    "UnknownMessageType",
    "ai_sample",
    "ask",
    "compare_releases",
    "enrich_presentation",
    "identify",
    "prepare",
    "test_data",
]
