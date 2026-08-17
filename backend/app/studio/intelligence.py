"""Message Intelligence — one search across MT tags and MX elements.

Everything here is deterministic dictionary lookup over the configured knowledge base and
the MX specifications. No LLM call is made, and none is needed: the answers are authored
data, not generated text.

A user can search by any of the things they actually have in front of them — a tag
(``95P``), a qualifier (``PSET``), an XML element (``SttlmDt``), an XPath fragment, a
business phrase (``settlement amount``) or a message type (``sese.023``).
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.domain.enums import MessageType
from app.knowledge.loader import knowledge_repository
from app.studio.catalogue import message_spec
from app.studio.models import (
    FieldExample,
    IntelligenceDetail,
    IntelligenceHit,
    IntelligenceSearchResponse,
    MessageFormat,
    Presence,
    SampleVariant,
    SpecField,
)
from app.studio.mx.registry import mx_registry
from app.studio.samples import build_sample

MAX_RESULTS = 60


@lru_cache(maxsize=1)
def _index() -> list[tuple[SpecField, list[str], set[str]]]:
    """Build the searchable index once: (field, message types, lowercase search terms)."""
    merged: dict[str, tuple[SpecField, list[str], set[str]]] = {}

    for message_type in sorted(MessageType, key=lambda item: item.value):
        spec = message_spec(MessageFormat.MT, message_type.value)
        for item in spec.fields:
            key = _merge_key(item)
            terms = _mt_terms(item)
            if key in merged:
                existing, types, existing_terms = merged[key]
                types.append(spec.message_type)
                existing_terms |= terms
                merged[key] = (existing, types, existing_terms)
            else:
                merged[key] = (item, [spec.message_type], terms)

    for mx_spec in mx_registry.all_specs():
        spec = message_spec(MessageFormat.MX, mx_spec.message_type)
        for item in spec.fields:
            merged[item.id] = (item, [spec.message_type], _mx_terms(item, mx_spec.message_type))
    return list(merged.values())


def _merge_key(field: SpecField) -> str:
    """MT rows that mean the same thing across message types collapse into one entry."""
    return f"MT|{field.sequence_code}|{field.tag}|{field.qualifier or ''}"


def _tokens(*values: str | None) -> set[str]:
    terms: set[str] = set()
    for value in values:
        if not value:
            continue
        lowered = value.lower()
        terms.add(lowered)
        terms.update(part for part in re.split(r"[^a-z0-9.]+", lowered) if len(part) > 1)
    return terms


def _mt_terms(field: SpecField) -> set[str]:
    terms = _tokens(
        field.tag,
        field.qualifier,
        field.display_name,
        field.business_path,
        field.sequence_code,
        field.business_meaning,
    )
    if field.tag and field.qualifier:
        terms.add(f"{field.tag}{field.qualifier}".lower())
        terms.add(f"{field.tag}/{field.qualifier}".lower())
        terms.add(f":{field.tag}::{field.qualifier}".lower())
    knowledge_terms = _knowledge_search_terms(field.id)
    terms |= _tokens(*knowledge_terms)
    terms.update(code.lower() for code in field.allowed_codes)
    return terms


def _knowledge_search_terms(row_id: str) -> list[str]:
    try:
        return knowledge_repository.get(row_id).search_terms
    except KeyError:
        return []


def _mx_terms(field: SpecField, message_type: str) -> set[str]:
    flat = mx_registry.by_path(message_type).get(field.id)
    element_terms = flat.element.search_terms if flat else []
    terms = _tokens(
        field.display_name,
        field.business_path,
        field.business_meaning,
        field.xpath,
        message_type,
        *element_terms,
    )
    if field.xpath:
        terms.update(part.lower() for part in field.xpath.split("/") if part)
        terms.add(field.xpath.lower())
    terms.update(code.lower() for code in field.allowed_codes)
    return terms


def _address(field: SpecField) -> str:
    if field.format is MessageFormat.MT:
        if field.qualifier:
            return f":{field.tag}::{field.qualifier}//  ({field.sequence_code})"
        return f":{field.tag}:  ({field.sequence_code})"
    return field.xpath or field.id


def _score(query: str, field: SpecField, terms: set[str], message_types: list[str]) -> int:
    """Rank exact identifier matches above prefix matches above substring matches.

    Returns 0 when nothing actually matched. Tie-breakers are only applied on top of a real
    match, never on their own — otherwise every mandatory field would surface for every
    query.
    """
    lowered = query.lower().strip()
    if not lowered:
        return 0

    identifier = ""
    if field.format is MessageFormat.MT:
        identifier = (field.qualifier or field.tag or "").lower()
    elif field.xpath:
        identifier = field.xpath.rsplit("/", 1)[-1].lower()

    score = 0
    if identifier == lowered:
        score += 120
    if field.format is MessageFormat.MT and (field.tag or "").lower() == lowered:
        score += 120
    if lowered in terms:
        score += 100
    if any(lowered == item.lower() for item in message_types):
        score += 60
    if any(term.startswith(lowered) for term in terms):
        score += 40
    if lowered in field.display_name.lower():
        score += 30
    if len(lowered) >= 3 and any(lowered in term for term in terms):
        score += 12
    if score == 0:
        return 0
    # Tie-breakers, applied only once something has genuinely matched.
    if field.presence is Presence.MANDATORY:
        score += 2
    return score


def search(
    query: str,
    *,
    format_: MessageFormat | None = None,
    message_type: str | None = None,
    limit: int = MAX_RESULTS,
) -> IntelligenceSearchResponse:
    hits: list[IntelligenceHit] = []
    for field, message_types, terms in _index():
        if format_ is not None and field.format is not format_:
            continue
        if message_type and message_type.upper() not in {
            item.upper() for item in message_types
        }:
            continue
        score = _score(query, field, terms, message_types)
        if score <= 0:
            continue
        hits.append(
            IntelligenceHit(
                id=field.id,
                format=field.format,
                message_types=sorted(message_types),
                label=field.display_name,
                address=_address(field),
                presence=field.presence,
                summary=field.business_meaning or field.technical_meaning,
                score=score,
            )
        )
    hits.sort(key=lambda item: (-item.score, item.label))
    return IntelligenceSearchResponse(query=query, total=len(hits), results=hits[:limit])


def detail(field_id: str) -> IntelligenceDetail:
    for field, message_types, _ in _index():
        if field.id != field_id:
            continue
        return _detail(field, message_types)
    # An MT row id addresses one message type directly; fall back to a direct lookup so a
    # caller holding a row id from the specification endpoint always gets an answer.
    for message_type in MessageType:
        spec = message_spec(MessageFormat.MT, message_type.value)
        for item in spec.fields:
            if item.id == field_id:
                return _detail(item, [spec.message_type])
    raise KeyError(f"Unknown field: {field_id}")


def _detail(field: SpecField, message_types: list[str]) -> IntelligenceDetail:
    cardinality = (
        f"{'1' if field.presence is Presence.MANDATORY else '0'}..{field.max_occurs}"
        if field.max_occurs > 1
        else f"{'1' if field.presence is Presence.MANDATORY else '0'}..1"
    )
    parent = None
    if field.format is MessageFormat.MX and field.xpath:
        parent = field.xpath.rsplit("/", 1)[0]
    else:
        parent = field.group_label
    return IntelligenceDetail(
        id=field.id,
        format=field.format,
        label=field.display_name,
        address=_address(field),
        message_types=sorted(message_types),
        presence=field.presence,
        business_meaning=field.business_meaning,
        technical_meaning=field.technical_meaning,
        why_used=field.why_used,
        format_explanation=field.format_explanation,
        allowed_codes=field.allowed_codes,
        # The same controlled vocabulary the form and the workbook use, so looking a code up
        # in Message Intelligence and choosing it in the builder cannot disagree.
        allowed_values=field.allowed_values,
        code_list=field.code_list,
        input_kind=field.input_kind,
        literal_prefix=field.literal_prefix,
        user_enters_literal_prefix=field.user_enters_literal_prefix,
        identifier_types=field.identifier_types,
        max_length=field.max_length,
        examples=field.examples or _fallback_examples(field),
        common_mistakes=field.common_mistakes,
        depends_on=field.depends_on,
        condition_explanation=field.condition_explanation,
        data_type=field.data_type,
        cardinality=cardinality,
        parent=parent,
        source_reference=field.source_reference,
        standards_release=field.standards_release,
        sample_lines=_sample_lines(field, message_types),
    )


def _fallback_examples(field: SpecField) -> list[FieldExample]:
    if not field.allowed_codes:
        return []
    return [
        FieldExample(
            value=item.code,
            explanation=item.description or f"{item.label}. A supported code for this field.",
        )
        for item in field.allowed_values[:4]
    ]


def _sample_lines(field: SpecField, message_types: list[str]) -> list[str]:
    """Show the field in context, taken from a real generated sample."""
    if not message_types:
        return []
    message_type = message_types[0]
    try:
        sample = build_sample(field.format, message_type, SampleVariant.TYPICAL)
    except (KeyError, ValueError):
        return []
    from app.profiles.loader import profiles
    from app.studio.models import GenerateRequest
    from app.studio.service import studio_service

    profiles.get("BASE_DEMO_V1")
    result = studio_service.generate(
        GenerateRequest(
            format=field.format,
            message_type=message_type,
            fields=sample.inputs,
            elements=sample.elements,
            persist=False,
        )
    )
    matches = [
        line.text.strip()
        for line in result.rendered_lines
        if line.field_id
        and (
            line.field_id == field.id
            or (
                field.format is MessageFormat.MT
                and line.field_id.endswith(f"-{field.tag}-{field.qualifier or 'NONE'}")
            )
        )
    ]
    return matches[:3]


def reset_index() -> None:
    """Drop the cached index. Used by tests that change the configuration."""
    _index.cache_clear()
