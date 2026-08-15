"""Sample data for every generatable message, in three depths.

Samples are *inputs*, not stored message text: they are field/element value sets pushed
through exactly the same composer the API uses. A sample therefore cannot drift away from
what the platform actually produces, and loading one into the builder gives a real editable
starting point rather than a read-only illustration.

``MINIMAL``  every mandatory field and nothing else
``TYPICAL``  the mandatory set plus the optional fields a real message usually carries
``FULL``     every field the configured subset supports

Two mechanisms keep samples honest:

* **Candidate-and-check** — each field offers several plausible values and the first one the
  platform's own validator accepts is used, so a sample never ships a value that would be
  rejected.
* **Validate-and-repair** — selection cannot know which conditional blocks a particular
  combination of values makes mandatory, because that knowledge lives in the validator. The
  candidate set is generated, validated, and any field the validator names as missing is
  added back, for a small fixed number of rounds.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from app.studio.catalogue import message_spec
from app.studio.models import (
    ElementInput,
    FieldInput,
    MessageFormat,
    MessageSpec,
    Presence,
    SampleMessage,
    SampleVariant,
    SpecField,
)

#: Fixed dates keep samples deterministic, which keeps golden tests and demos stable.
TRADE_DATE = date(2026, 8, 14)
SETTLEMENT_DATE = date(2026, 8, 18)

#: Values chosen per business path so the MT and MX samples describe the same trade.
BUSINESS_VALUES: dict[str, dict[MessageFormat, str]] = {
    "senderReference": {MessageFormat.MT: "TESTREF001", MessageFormat.MX: "TESTREF001"},
    "relatedReference": {MessageFormat.MT: "TESTREF001", MessageFormat.MX: "TESTREF001"},
    "clientReference": {MessageFormat.MT: "COMMONREF001", MessageFormat.MX: "COMMONREF001"},
    "function": {MessageFormat.MT: "NEWM"},
    "trade.tradeDate": {
        MessageFormat.MT: TRADE_DATE.strftime("%Y%m%d"),
        MessageFormat.MX: TRADE_DATE.isoformat(),
    },
    "trade.settlementDate": {
        MessageFormat.MT: SETTLEMENT_DATE.strftime("%Y%m%d"),
        MessageFormat.MX: SETTLEMENT_DATE.isoformat(),
    },
    "confirmation.actualSettlementDate": {
        MessageFormat.MT: SETTLEMENT_DATE.strftime("%Y%m%d"),
        MessageFormat.MX: SETTLEMENT_DATE.isoformat(),
    },
    "security.identifier": {
        MessageFormat.MT: "ISIN XS0000000001",
        MessageFormat.MX: "XS0000000001",
    },
    "security.description": {MessageFormat.MX: "SYNTHETIC TEST BOND 2030"},
    "security.quantity": {MessageFormat.MT: "UNIT/1000", MessageFormat.MX: "1000"},
    "confirmation.settledQuantity": {MessageFormat.MT: "UNIT/1000", MessageFormat.MX: "1000"},
    "account.safekeepingAccount": {
        MessageFormat.MT: "SAFE0000001",
        MessageFormat.MX: "SAFE0000001",
    },
    "settlement.amount": {MessageFormat.MT: "USD25000,00", MessageFormat.MX: "USD 25000.00"},
    "confirmation.settledAmount": {
        MessageFormat.MT: "USD25000,00",
        MessageFormat.MX: "USD 25000.00",
    },
    "settlement.cashDirection": {MessageFormat.MX: "DBIT"},
    "settlement.placeOfSettlement": {
        MessageFormat.MT: "CSD/DEMOPSET01",
        MessageFormat.MX: "DEMOGB2LXXX",
    },
    "settlement.deliveringAgent": {
        MessageFormat.MT: "AGT/DEMODEAG01",
        MessageFormat.MX: "DEMODEAGXXX",
    },
    "settlement.receivingAgent": {
        MessageFormat.MT: "AGT/DEMOREAG01",
        MessageFormat.MX: "DEMOREAGXXX",
    },
    "direction": {MessageFormat.MX: "RECE"},
    "paymentType": {MessageFormat.MX: "APMT"},
    "trade.transactionType": {MessageFormat.MX: "TRAD"},
}

#: MT direction and transaction-type codes vary by message type.
MT_DIRECTION_BY_TYPE: dict[str, tuple[str, str]] = {
    "MT540": ("RECE", "BUY"),
    "MT541": ("RECE", "BUY"),
    "MT542": ("DELI", "SELL"),
    "MT543": ("DELI", "SELL"),
    "MT544": ("RECE", "BUY"),
    "MT545": ("RECE", "BUY"),
    "MT546": ("DELI", "SELL"),
    "MT547": ("DELI", "SELL"),
}

#: The optional fields a TYPICAL message normally carries, by business path.
TYPICAL_OPTIONAL_PATHS = frozenset(
    {
        "clientReference",
        "trade.tradeDate",
        "security.description",
        "settlement.placeOfSettlement",
        "settlement.deliveringAgent",
        "settlement.receivingAgent",
    }
)

#: Deterministic fallbacks by MT tag, used when nothing better is available.
MT_TAG_FALLBACKS: dict[str, str] = {
    "20C": "TESTREF001",
    "98A": SETTLEMENT_DATE.strftime("%Y%m%d"),
    "35B": "ISIN XS0000000001",
    "36B": "UNIT/1000",
    "93B": "UNIT/1000",
    "97A": "SAFE0000001",
    "95R": "AGT/DEMOPARTY1",
    "19A": "USD25000,00",
    "19B": "USD25000,00",
    "11A": "USD",
    "13A": "001",
    "17B": "Y",
    "28E": "1/ONLY",
    "99A": "1",
    "70D": "SYNTHETIC TEST NARRATIVE",
    "70E": "SYNTHETIC TEST NARRATIVE",
}

MX_TYPE_FALLBACKS: dict[str, str] = {
    "ISODate": SETTLEMENT_DATE.isoformat(),
    "ISODateTime": f"{SETTLEMENT_DATE.isoformat()}T00:00:00Z",
    "DecimalNumber": "1000",
    "ActiveCurrencyAndAmount": "USD 25000.00",
    "ISINOct2015Identifier": "XS0000000001",
    "AnyBICDec2014Identifier": "DEMOGB2LXXX",
    "LEIIdentifier": "DEMO00000000000000XX",
    "YesNoIndicator": "true",
    "Exact4AlphaNumericText": "TEST",
}

MAX_REPAIR_ROUNDS = 6


# --------------------------------------------------------------------------------------
# Value selection
# --------------------------------------------------------------------------------------


def _candidates(field: SpecField, message_type: str) -> list[str]:
    """Every plausible value for one field, best first."""
    options: list[str] = []
    path = field.business_path
    if path and field.format is MessageFormat.MT:
        if path == "direction":
            options.append(MT_DIRECTION_BY_TYPE.get(message_type, ("RECE", "BUY"))[0])
        elif path == "trade.transactionType":
            options.append(MT_DIRECTION_BY_TYPE.get(message_type, ("RECE", "BUY"))[1])
    if path:
        by_format = BUSINESS_VALUES.get(path, {})
        if field.format in by_format:
            options.append(by_format[field.format])
    options.extend(example.value for example in field.examples)
    options.extend(field.allowed_codes)
    if field.format is MessageFormat.MT:
        fallback = MT_TAG_FALLBACKS.get(field.tag or "")
    else:
        fallback = MX_TYPE_FALLBACKS.get(field.data_type or "")
        if fallback is None and (field.data_type or "").startswith("Max"):
            fallback = "SYNTHETICVALUE"
    if fallback:
        options.append(fallback)
    return list(dict.fromkeys(option for option in options if option))


def _mt_acceptable(field: SpecField, value: str) -> bool:
    from app.authoring.composer import _format_valid

    if not _format_valid(field.tag or "", value):
        return False
    direct_code = (field.tag or "")[:2] in {"11", "17", "22", "23", "24", "25"}
    return not (direct_code and field.allowed_codes and value not in field.allowed_codes)


def _mx_acceptable(field: SpecField, message_type: str, value: str) -> bool:
    from app.studio.mx.generator import validate_value
    from app.studio.mx.registry import mx_registry

    flat = mx_registry.by_path(message_type).get(field.id)
    if flat is None:
        return True
    _, issue = validate_value(flat, value)
    return issue is None


def _sample_value(field: SpecField, message_type: str) -> str | None:
    """Return the first candidate the platform's own validation accepts."""
    candidates = _candidates(field, message_type)
    for candidate in candidates:
        acceptable = (
            _mt_acceptable(field, candidate)
            if field.format is MessageFormat.MT
            else _mx_acceptable(field, message_type, candidate)
        )
        if acceptable:
            return candidate
    return candidates[0] if candidates else None


# --------------------------------------------------------------------------------------
# Field selection
# --------------------------------------------------------------------------------------


def _choice_parent(branch: str) -> str:
    return branch.rsplit("/", 1)[0]


def _initial_selection(spec: MessageSpec, variant: SampleVariant) -> set[str]:
    chosen: set[str] = set()
    branch_per_choice: dict[str, str] = {}
    for field in sorted(spec.fields, key=lambda item: item.order):
        include = field.presence is Presence.MANDATORY
        if variant is not SampleVariant.MINIMAL and field.business_path in TYPICAL_OPTIONAL_PATHS:
            include = True
        if variant is SampleVariant.FULL:
            include = True
        if not include:
            continue
        if field.choice_group:
            # Only one branch of a choice may be present, so keep the first one seen.
            parent = _choice_parent(field.choice_group)
            existing = branch_per_choice.setdefault(parent, field.choice_group)
            if existing != field.choice_group:
                continue
        chosen.add(field.id)
    return chosen


def _apply_consistency(
    spec: MessageSpec, pairs: list[tuple[SpecField, str]]
) -> list[tuple[SpecField, str]]:
    """Drop fields that the chosen values make invalid."""
    values = {field.business_path: value for field, value in pairs if field.business_path}
    payment = values.get("paymentType")
    direction = values.get("direction")
    result: list[tuple[SpecField, str]] = []
    for field, value in pairs:
        if payment == "FREE" and field.business_path in {
            "settlement.amount",
            "confirmation.settledAmount",
            "settlement.cashDirection",
        }:
            continue
        if spec.format is MessageFormat.MX:
            # A receipt names the delivering chain; a delivery names the receiving chain.
            if direction == "RECE" and "/RcvgSttlmPties/" in field.id:
                continue
            if direction == "DELI" and "/DlvrgSttlmPties/" in field.id:
                continue
        result.append((field, value))
    return result


def _valued(
    spec: MessageSpec, chosen_ids: set[str], message_type: str
) -> list[tuple[SpecField, str]]:
    pairs: list[tuple[SpecField, str]] = []
    for field in sorted(spec.fields, key=lambda item: item.order):
        if field.id not in chosen_ids:
            continue
        value = _sample_value(field, message_type)
        if value is not None:
            pairs.append((field, value))
    return _apply_consistency(spec, pairs)


def _to_request_inputs(
    format_: MessageFormat, pairs: list[tuple[SpecField, str]]
) -> tuple[list[FieldInput], list[ElementInput]]:
    if format_ is MessageFormat.MT:
        return (
            [
                FieldInput(
                    id=field.id,
                    sequence=field.sequence_code,
                    tag=field.tag,
                    qualifier=field.qualifier,
                    option=field.option,
                    value=value,
                )
                for field, value in pairs
            ],
            [],
        )
    return [], [ElementInput(path=field.id, value=value) for field, value in pairs]


def _fields_named_by_validator(
    format_: MessageFormat,
    message_type: str,
    pairs: list[tuple[SpecField, str]],
    by_id: dict[str, SpecField],
    already: set[str],
) -> set[str]:
    """Ask the real validator what is missing and map its answer back to field ids."""
    from app.studio.models import GenerateRequest
    from app.studio.service import studio_service

    fields, elements = _to_request_inputs(format_, pairs)
    result = studio_service.generate(
        GenerateRequest(
            format=format_,
            message_type=message_type,
            scenario_id="SAMPLE",
            fields=fields,
            elements=elements,
            persist=False,
        )
    )
    additions: set[str] = set()
    for issue in result.validation.errors:
        for hint in (issue.location, issue.expected):
            candidate = by_id.get(hint or "")
            if candidate is not None and candidate.id not in already:
                additions.add(candidate.id)
    return additions


def _selected_fields(
    format_: MessageFormat, message_type: str, variant: SampleVariant
) -> list[tuple[SpecField, str]]:
    spec = message_spec(format_, message_type)
    by_id = {field.id: field for field in spec.fields}
    chosen_ids = _initial_selection(spec, variant)
    for _ in range(MAX_REPAIR_ROUNDS):
        pairs = _valued(spec, chosen_ids, message_type)
        additions = _fields_named_by_validator(format_, message_type, pairs, by_id, chosen_ids)
        if not additions:
            break
        chosen_ids |= additions
    return _valued(spec, chosen_ids, message_type)


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=256)
def build_sample(
    format_: MessageFormat, message_type: str, variant: SampleVariant
) -> SampleMessage:
    spec = message_spec(format_, message_type)
    pairs = _selected_fields(format_, message_type, variant)
    titles = {
        SampleVariant.MINIMAL: "Minimal valid",
        SampleVariant.TYPICAL: "Typical",
        SampleVariant.FULL: "Full configured subset",
    }
    descriptions = {
        SampleVariant.MINIMAL: "Every mandatory field and nothing else — the smallest "
        f"{spec.message_type} that validates.",
        SampleVariant.TYPICAL: "The mandatory fields plus the optional fields a real "
        f"{spec.message_type} usually carries.",
        SampleVariant.FULL: "Every field the configured subset supports, so you can see the "
        "complete shape of the message.",
    }
    fields, elements = _to_request_inputs(format_, pairs)
    return SampleMessage(
        sample_id=f"{spec.message_type}-{variant.value}",
        format=format_,
        message_type=spec.message_type,
        variant=variant,
        title=titles[variant],
        description=descriptions[variant],
        field_count=len(pairs),
        inputs=fields,
        elements=elements,
    )


@lru_cache(maxsize=64)
def available_variants(format_: MessageFormat, message_type: str) -> tuple[SampleVariant, ...]:
    """Return only variants that produce something distinct and non-empty."""
    variants: list[SampleVariant] = []
    seen_sizes: set[int] = set()
    for variant in SampleVariant:
        sample = build_sample(format_, message_type, variant)
        if sample.field_count == 0:
            continue
        if sample.field_count in seen_sizes and variant is not SampleVariant.MINIMAL:
            continue
        seen_sizes.add(sample.field_count)
        variants.append(variant)
    return tuple(variants)


def sample_dates() -> tuple[date, date]:
    """The fixed sample dates, for documentation and Excel templates."""
    return TRADE_DATE, SETTLEMENT_DATE


def future_settlement_dates() -> tuple[date, date]:
    """Trade and settlement dates relative to today, for Excel templates."""
    today = datetime.now(UTC).date()
    return today, today + timedelta(days=2)
