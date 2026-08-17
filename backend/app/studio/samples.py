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

from app.domain.identifiers import synthetic_isin
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

#: The sample instrument, with its ISO 6166 check digit computed rather than typed.
#:
#: The previous value, ``XS0000000001``, was checksum-invalid — its correct final digit is
#: 9 — so every sample, every golden fixture and both Excel templates shipped an identifier
#: the studio itself now rejects. Deriving it means that cannot happen again.
#:
#: STRUCTURALLY_VALID_SYNTHETIC: the shape and the check digit are right. It is not
#: registered with any national numbering agency and must never be presented as though it
#: were.
SAMPLE_ISIN = synthetic_isin("XS000000000")

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
    # One value for both formats. MT used to need its own entry carrying "ISIN " because
    # the caller owned that literal; the composer owns it now, so the business value is the
    # same in ISO 15022 and ISO 20022.
    "security.identifier": {
        MessageFormat.MT: SAMPLE_ISIN,
        MessageFormat.MX: SAMPLE_ISIN,
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
    # Settlement parties are identified by BIC in both formats now that MT offers option
    # P, so the two samples describe the same counterparties rather than parallel ones.
    # Structurally valid, deliberately synthetic, not registered with SWIFT.
    "settlement.placeOfSettlement": {
        MessageFormat.MT: "DEMOGB2LXXX",
        MessageFormat.MX: "DEMOGB2LXXX",
    },
    "settlement.deliveringAgent": {
        MessageFormat.MT: "DEMODEAGXXX",
        MessageFormat.MX: "DEMODEAGXXX",
    },
    "settlement.receivingAgent": {
        MessageFormat.MT: "DEMOREAGXXX",
        MessageFormat.MX: "DEMOREAGXXX",
    },
    "direction": {MessageFormat.MX: "RECE"},
    "paymentType": {MessageFormat.MX: "APMT"},
    # An ordinary settlement of a trade, in both formats. MT no longer carries direction in
    # a field at all — the message type states it.
    "trade.transactionType": {MessageFormat.MT: "TRAD", MessageFormat.MX: "TRAD"},
}

#: Which securities movement each MT describes. Used only to choose the MX direction
#: value; in MT the message type carries it and no field restates it.
MT_MOVEMENT_BY_TYPE: dict[str, str] = {
    "MT540": "RECE",
    "MT541": "RECE",
    "MT542": "DELI",
    "MT543": "DELI",
    "MT544": "RECE",
    "MT545": "RECE",
    "MT546": "DELI",
    "MT547": "DELI",
}

#: The optional fields a TYPICAL message normally carries, by business path.
#:
#: The settlement agents are deliberately absent. Whichever agent the message actually needs
#: is MANDATORY for that message type — the delivering agent on a receipt, the receiving
#: agent on a delivery — so it is always included. Listing both here put the *other* chain
#: into every typical sample, which is what taught a tester that an MT541 names a receiving
#: agent. The FULL variant still shows both, because showing the whole configured subset is
#: what it is for.
TYPICAL_OPTIONAL_PATHS = frozenset(
    {
        "clientReference",
        "trade.tradeDate",
        "security.description",
        "settlement.placeOfSettlement",
    }
)

#: Deterministic fallbacks by MT tag, used when nothing better is available.
MT_TAG_FALLBACKS: dict[str, str] = {
    "20C": "TESTREF001",
    "98A": SETTLEMENT_DATE.strftime("%Y%m%d"),
    "35B": SAMPLE_ISIN,
    "36B": "UNIT/1000",
    "93B": "UNIT/1000",
    "97A": "SAFE0000001",
    "95P": "DEMOGB2LXXX",
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
    "ISINOct2015Identifier": SAMPLE_ISIN,
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
    if path == "direction" and field.format is MessageFormat.MX:
        options.append(MT_MOVEMENT_BY_TYPE.get(message_type, "RECE"))
    # A field that declares its own example knows more than the cross-message table. This
    # matters where one message carries both a sender's own reference and a reference to a
    # previous message: the generic table gives both the same value, so the sample would
    # demonstrate exactly the mistake the field's guidance warns against. MT keeps the table
    # first because its samples are pinned by golden files.
    prefer_own_example = field.format is MessageFormat.MX and bool(field.examples)
    if prefer_own_example:
        options.extend(example.value for example in field.examples)
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


def _mt_acceptable(field: SpecField, message_type: str, value: str) -> bool:
    """Whether the platform's own validation accepts this value for this field.

    Runs against the real specification row, so a candidate that would fail the identifier
    check digit or the option-R data source scheme is rejected here rather than shipped in
    a sample and then refused at generation.
    """
    from app.authoring.composer import row_format_valid
    from app.domain.enums import MessageType
    from app.knowledge.presentation import is_direct_code_field
    from app.specifications.registry import specification_registry

    row = next(
        (
            item
            for item in specification_registry.get(MessageType(message_type)).fields
            if item.row_id == field.id
        ),
        None,
    )
    if row is None:
        return True
    if not row_format_valid(row, value):
        return False
    if row.literal_prefix and "ISIN" in row.identifier_types:
        from app.domain.identifiers import validate_isin

        if not validate_isin(value).check_digit_valid:
            return False
    return not (
        is_direct_code_field(row.tag, row.allowed_codes) and value not in row.allowed_codes
    )


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
            _mt_acceptable(field, message_type, candidate)
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
