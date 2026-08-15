import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.agents.errors import AiServiceError, ai_error
from app.agents.preprocessing import SanitizedInput, resolve_placeholder
from app.agents.schemas import (
    ExtractableFieldPath,
    ExtractionSource,
    GroundedExtractedField,
    IntentField,
    MissingDecision,
    ModelInterpretationResult,
)
from app.domain.enums import (
    CanonicalFieldPath,
    Direction,
    Lifecycle,
    MessageFunction,
    PaymentType,
    ResponseAction,
    TransactionType,
)

RAW_MT_PATTERN = re.compile(
    r"(?:\{[1345]:|\{2:(?:MT|I|O)?54[0-8]|:\d{2}[A-Z]?:|\bMT54[0-8]\b)",
    re.IGNORECASE,
)
HIDDEN_INSTRUCTION_PATTERN = re.compile(
    r"(?:system prompt|hidden prompt|authorization\s*:\s*bearer|chain of thought)",
    re.IGNORECASE,
)
DECIMAL_PATHS = {
    CanonicalFieldPath.SECURITY_QUANTITY,
    CanonicalFieldPath.SETTLEMENT_AMOUNT,
    CanonicalFieldPath.SETTLED_QUANTITY,
    CanonicalFieldPath.SETTLED_AMOUNT,
}
DATE_PATHS = {
    CanonicalFieldPath.TRADE_DATE,
    CanonicalFieldPath.SETTLEMENT_DATE,
    CanonicalFieldPath.ACTUAL_SETTLEMENT_DATE,
}
PLACEHOLDER_KINDS = {
    CanonicalFieldPath.SECURITY_IDENTIFIER: {"ISIN"},
    CanonicalFieldPath.SAFEKEEPING_ACCOUNT: {"SAFEKEEPING_ACCOUNT"},
    CanonicalFieldPath.SENDER_REFERENCE: {"SENDER_REFERENCE", "BUSINESS_REFERENCE"},
    CanonicalFieldPath.RELATED_REFERENCE: {"RELATED_REFERENCE"},
    CanonicalFieldPath.CLIENT_REFERENCE: {"CLIENT_REFERENCE"},
    CanonicalFieldPath.PLACE_OF_SETTLEMENT: {"PARTY_ID", "PARTY_NAME", "BIC"},
    CanonicalFieldPath.DELIVERING_AGENT: {"PARTY_ID", "PARTY_NAME", "BIC"},
    CanonicalFieldPath.RECEIVING_AGENT: {"PARTY_ID", "PARTY_NAME", "BIC"},
}
NUMBER_PATTERN = re.compile(r"(?<![A-Z0-9])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def validate_model_payload(
    payload: dict[str, Any],
    sanitised: SanitizedInput,
) -> ModelInterpretationResult:
    try:
        result = ModelInterpretationResult.model_validate(payload)
    except ValidationError as exc:
        failure_paths = tuple(
            "$"
            + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error["loc"])
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ai_error("AI_SCHEMA_VALIDATION_FAILED", failure_paths=failure_paths) from exc
    _reconcile_controlled_intent(result, sanitised.text)
    _reconcile_explicit_fields(result, sanitised)
    _reconcile_missing_decisions(result, sanitised.text)
    _reject_raw_mt(result)
    extracted_paths = [item.field_path for item in result.extracted_fields]
    if len(extracted_paths) != len(set(extracted_paths)):
        raise _unsafe("$.extractedFields:duplicateFieldPath")
    for extracted in result.extracted_fields:
        _validate_extracted_field(extracted, sanitised)
    _validate_ambiguity_contract(result)
    return result


def rehydrate_value(
    extracted: GroundedExtractedField,
    sanitised: SanitizedInput,
) -> str:
    if extracted.source == ExtractionSource.PLACEHOLDER:
        issued = resolve_placeholder(
            extracted.value,
            extracted.placeholder_id,
            sanitised.placeholders,
        )
        path = CanonicalFieldPath(extracted.field_path.value)
        allowed = PLACEHOLDER_KINDS.get(path, set())
        if issued.kind not in allowed:
            raise _unsafe(f"$.extractedFields.{extracted.field_path.value}:placeholderType")
        return issued.original
    return extracted.value


def _reject_raw_mt(result: ModelInterpretationResult) -> None:
    strings: list[str] = [
        result.interpretation_summary,
        *result.ambiguities,
        *result.missing_decisions,
        *(item.value for item in result.extracted_fields),
    ]
    if any(
        RAW_MT_PATTERN.search(value) or HIDDEN_INSTRUCTION_PATTERN.search(value)
        for value in strings
    ):
        raise _unsafe("$:forbiddenContent")
    narratives = [result.interpretation_summary, *result.ambiguities]
    if any(
        any(character.isdigit() for character in value) or "[[SMS_" in value for value in narratives
    ):
        raise _unsafe("$.interpretationSummary:financialValue")


def _validate_extracted_field(
    extracted: GroundedExtractedField,
    sanitised: SanitizedInput,
) -> None:
    path = CanonicalFieldPath(extracted.field_path.value)
    if extracted.source == ExtractionSource.PLACEHOLDER:
        if extracted.evidence_start is not None or extracted.evidence_end is not None:
            raise _unsafe(f"$.extractedFields.{extracted.field_path.value}:placeholderOffsets")
        rehydrate_value(extracted, sanitised)
        return
    if extracted.value.startswith("[[SMS_"):
        raise _unsafe(f"$.extractedFields.{extracted.field_path.value}:unexpectedPlaceholder")
    if extracted.placeholder_id is not None:
        raise _unsafe(f"$.extractedFields.{extracted.field_path.value}:unexpectedPlaceholderId")
    span = _verified_grounding_span(path, extracted.value, sanitised.text, extracted)
    if span is None:
        raise _unsafe(f"$.extractedFields.{extracted.field_path.value}:ungroundedValue")
    extracted.evidence_start, extracted.evidence_end = span


def _is_grounded(path: CanonicalFieldPath, value: str, evidence: str) -> bool:
    if path in DECIMAL_PATHS:
        try:
            parsed_value = Decimal(value.replace(",", ""))
            grounded_value = Decimal(re.sub(r"[^0-9.\-]", "", evidence).replace(",", ""))
            return parsed_value.is_finite() and parsed_value > 0 and parsed_value == grounded_value
        except InvalidOperation:
            return False
    if path in DATE_PATHS:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return False
        return value in evidence or parsed.strftime("%Y-%m-%d") in evidence
    normalized_value = " ".join(value.casefold().split())
    normalized_evidence = " ".join(evidence.casefold().split())
    return normalized_value == normalized_evidence or normalized_value in normalized_evidence


def _verified_grounding_span(
    path: CanonicalFieldPath,
    value: str,
    text: str,
    extracted: GroundedExtractedField,
) -> tuple[int, int] | None:
    if extracted.evidence_start is not None and extracted.evidence_end is not None:
        start = extracted.evidence_start
        end = extracted.evidence_end
        if 0 <= start < end <= len(text):
            evidence = text[start:end]
            if _is_grounded(path, value, evidence) and _has_business_cue(path, text, start, end):
                return start, end

    if path in DECIMAL_PATHS:
        try:
            expected = Decimal(value.replace(",", ""))
        except InvalidOperation:
            return None
        if not expected.is_finite() or expected <= 0:
            return None
        for match in NUMBER_PATTERN.finditer(text):
            try:
                candidate = Decimal(match.group().replace(",", ""))
            except InvalidOperation:
                continue
            if candidate == expected and _has_business_cue(path, text, match.start(), match.end()):
                return match.span()
        return None

    if path in DATE_PATHS:
        try:
            date.fromisoformat(value)
        except ValueError:
            return None
        date_match = re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text)
        return date_match.span() if date_match else None

    string_match = re.search(re.escape(value), text, re.IGNORECASE)
    return string_match.span() if string_match else None


def _has_business_cue(path: CanonicalFieldPath, text: str, start: int, end: int) -> bool:
    context = text[max(0, start - 24) : min(len(text), end + 24)]
    if path in {CanonicalFieldPath.SECURITY_QUANTITY, CanonicalFieldPath.SETTLED_QUANTITY}:
        return bool(
            re.search(
                r"\b(?:shares?|securities|securites|bonds?|units?|quantity)\b",
                context,
                re.I,
            )
        )
    if path in {CanonicalFieldPath.SETTLEMENT_AMOUNT, CanonicalFieldPath.SETTLED_AMOUNT}:
        return bool(
            re.search(
                r"(?:[$€£]|\b(?:USD|EUR|GBP|amount|value|consideration|cash|payment)\b)",
                context,
                re.I,
            )
        )
    return True


def _validate_ambiguity_contract(result: ModelInterpretationResult) -> None:
    missing = set(result.missing_decisions)
    if result.intent.lifecycle is None and MissingDecision.LIFECYCLE not in missing:
        raise _unsafe("$.missingDecisions:lifecycle")
    if result.intent.lifecycle is None or result.intent.lifecycle.value == "INSTRUCTION":
        if result.intent.direction is None and MissingDecision.DIRECTION not in missing:
            raise _unsafe("$.missingDecisions:direction")
        if result.intent.payment_type is None and MissingDecision.PAYMENT_TYPE not in missing:
            raise _unsafe("$.missingDecisions:paymentType")
    inferred = set(result.intent.inferred_fields)
    allowed = {
        IntentField.LIFECYCLE,
        IntentField.DIRECTION,
        IntentField.PAYMENT_TYPE,
        IntentField.TRANSACTION_TYPE,
        IntentField.FUNCTION,
        IntentField.RESPONSE_ACTION,
    }
    if not inferred.issubset(allowed):
        raise _unsafe("$.intent.inferredFields")
    if inferred and not result.requires_clarification:
        raise _unsafe("$.requiresClarification:inferredFields")
    if (result.missing_decisions or result.ambiguities) and not result.requires_clarification:
        raise _unsafe("$.requiresClarification:missingOrAmbiguous")


def _unsafe(path: str) -> AiServiceError:
    return ai_error("AI_UNSAFE_RESPONSE", failure_paths=(path,))


def _reconcile_controlled_intent(result: ModelInterpretationResult, text: str) -> None:
    """Make high-confidence controlled vocabulary authoritative and auditable."""
    lowered = text.casefold()
    explicit_receive = bool(
        re.search(
            r"\b(?:receive|receiving|incoming|receipt|rvp|recieve)\b"
            r"(?!\s+(?:payment|agent|party))",
            lowered,
        )
    )
    explicit_deliver = bool(
        re.search(r"\b(?:deliver|delivery|delivered|outgoing)\b", lowered)
        or re.search(r"\bdelivering\b(?!\s+(?:agent|party))", lowered)
        or re.search(r"\b(?:shares?|securities|position)\s+out\b", lowered)
        or re.search(r"\bsend\s+(?:the\s+)?securities\s+out\b", lowered)
    )
    free = bool(
        re.search(
            r"\b(?:fop|free[- ]of[- ]payment|without payment|no cash(?: leg)?)\b",
            lowered,
        )
    )
    against = bool(
        re.search(
            r"\b(?:dvp|rvp|against[- ]payment|aganst[- ]payment|with payment|"
            r"receive payment|(?<!no )cash leg)\b",
            lowered,
        )
        or re.search(r"\b(?:USD|EUR|GBP)\b\s+\d", text)
    )
    buy = bool(re.search(r"\b(?:buy|bought|buying|purchase|purchased)\b", lowered))
    sell = bool(re.search(r"\b(?:sell|sold|selling|sale)\b", lowered))
    if not sell and explicit_deliver and "receive payment" in lowered:
        sell = True

    confirmation = bool(re.search(r"\b(?:confirm|confirmation|partially confirm)\b", lowered))
    status = bool(
        re.search(
            r"\b(?:status|advice|pending|waiting|rejected|matched|unmatched|"
            r"could not be processed|failed processing)\b",
            lowered,
        )
    )
    cancellation = bool(re.search(r"\b(?:cancel|cancelled|cancellation)\b", lowered))
    cancellation_command = bool(re.search(r"\b(?:cancel|cancelled)\b", lowered))
    reversal = bool(re.search(r"\b(?:reverse|reversal)\b", lowered))
    complex_lifecycle = (confirmation and status) or (
        cancellation_command and (confirmation or status)
    )
    pure_injection = "[UNTRUSTED_DIRECTIVE_REMOVED]" in text and not any(
        (explicit_receive, explicit_deliver, free, against, buy, sell, confirmation, status)
    )

    inferred: set[IntentField] = set(result.intent.inferred_fields)
    if pure_injection:
        result.intent.lifecycle = None
        result.intent.direction = None
        result.intent.payment_type = None
        result.intent.transaction_type = None
        result.intent.function = None
        result.intent.response_action = None
        inferred.clear()
    elif complex_lifecycle:
        result.intent.lifecycle = None
        result.intent.response_action = None
    elif status:
        result.intent.lifecycle = Lifecycle.STATUS
    elif confirmation:
        result.intent.lifecycle = Lifecycle.CONFIRMATION
    elif any(
        (explicit_receive, explicit_deliver, free, against, buy, sell, cancellation, reversal)
    ):
        result.intent.lifecycle = Lifecycle.INSTRUCTION
        if cancellation:
            result.intent.function = MessageFunction.CANC
        elif reversal:
            result.intent.function = MessageFunction.REVR
        else:
            result.intent.function = MessageFunction.NEWM
    elif re.fullmatch(
        r"\s*\d[\d,.]*\s+(?:shares?|securities|securites|units?|bonds?)[.]?\s*",
        lowered,
    ):
        result.intent.lifecycle = None
        result.intent.function = None

    if explicit_receive and explicit_deliver:
        result.intent.direction = None
    elif explicit_receive:
        result.intent.direction = Direction.RECEIVE
        inferred.discard(IntentField.DIRECTION)
    elif explicit_deliver:
        result.intent.direction = Direction.DELIVER
        inferred.discard(IntentField.DIRECTION)
    elif buy and against:
        result.intent.direction = Direction.RECEIVE
        inferred.add(IntentField.DIRECTION)
    elif sell and against:
        result.intent.direction = Direction.DELIVER
        inferred.add(IntentField.DIRECTION)
    elif result.intent.lifecycle in {Lifecycle.CONFIRMATION, Lifecycle.STATUS}:
        result.intent.direction = None

    if free and against:
        result.intent.payment_type = None
    elif free:
        result.intent.payment_type = PaymentType.FREE_OF_PAYMENT
        inferred.discard(IntentField.PAYMENT_TYPE)
    elif against:
        result.intent.payment_type = PaymentType.AGAINST_PAYMENT
        inferred.discard(IntentField.PAYMENT_TYPE)
    elif result.intent.lifecycle in {Lifecycle.CONFIRMATION, Lifecycle.STATUS}:
        result.intent.payment_type = None

    if buy and not sell:
        result.intent.transaction_type = TransactionType.BUY
        inferred.discard(IntentField.TRANSACTION_TYPE)
    elif sell and not buy:
        result.intent.transaction_type = TransactionType.SELL
        inferred.discard(IntentField.TRANSACTION_TYPE)

    if result.intent.lifecycle == Lifecycle.CONFIRMATION:
        result.intent.response_action = (
            ResponseAction.PARTIAL_CONFIRMATION
            if re.search(r"\b(?:partial|partially)\b", lowered)
            else ResponseAction.FULL_CONFIRMATION
        )
    elif result.intent.lifecycle == Lifecycle.STATUS:
        if re.search(r"\bcancellation\b.*\brejected\b", lowered):
            result.intent.response_action = ResponseAction.CANCELLATION_REJECTED_STATUS
        elif re.search(r"\bcancellation\b.*\baccepted\b", lowered):
            result.intent.response_action = ResponseAction.CANCELLATION_ACCEPTED_STATUS
        elif re.search(r"\bunmatched\b", lowered):
            result.intent.response_action = ResponseAction.UNMATCHED_STATUS
        elif re.search(r"\bmatched\b", lowered):
            result.intent.response_action = ResponseAction.MATCHED_STATUS
        elif re.search(r"\b(?:rejected|could not be processed|failed processing)\b", lowered):
            result.intent.response_action = ResponseAction.REJECTED_STATUS
        elif re.search(r"\b(?:pending|waiting)\b", lowered):
            result.intent.response_action = ResponseAction.PENDING_STATUS

    controlled = {
        IntentField.LIFECYCLE,
        IntentField.DIRECTION,
        IntentField.PAYMENT_TYPE,
        IntentField.TRANSACTION_TYPE,
        IntentField.FUNCTION,
        IntentField.RESPONSE_ACTION,
    }
    if result.intent.lifecycle is not None:
        inferred.discard(IntentField.LIFECYCLE)
    result.intent.inferred_fields = sorted(
        inferred.intersection(controlled), key=lambda item: item.value
    )


def _reconcile_explicit_fields(
    result: ModelInterpretationResult,
    sanitised: SanitizedInput,
) -> None:
    text = sanitised.text
    lowered = text.casefold()
    confirmation = result.intent.lifecycle == Lifecycle.CONFIRMATION
    local: dict[ExtractableFieldPath, GroundedExtractedField] = {}

    def add_explicit(path: ExtractableFieldPath, value: str, start: int, end: int) -> None:
        local[path] = GroundedExtractedField(
            field_path=path,
            value=value,
            source=ExtractionSource.EXPLICIT,
            evidence_start=start,
            evidence_end=end,
            placeholder_id=None,
        )

    quantity_pattern = re.compile(
        r"(?P<value>\d[\d,]*(?:\.\d+)?)\s+"
        r"(?:(?:units?|shares?)\s+of\s+)?(?:securities|security|securites|shares|bonds?|units?)\b",
        re.IGNORECASE,
    )
    for match in quantity_pattern.finditer(text):
        path = (
            ExtractableFieldPath.SETTLED_QUANTITY
            if confirmation
            else ExtractableFieldPath.SECURITY_QUANTITY
        )
        add_explicit(
            path,
            match.group("value").replace(",", ""),
            match.start("value"),
            match.end("value"),
        )

    cash_pattern = re.compile(
        r"\b(?P<currency>USD|EUR|GBP)\b\s+(?P<amount>\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for match in cash_pattern.finditer(text):
        add_explicit(
            ExtractableFieldPath.SETTLEMENT_CURRENCY,
            match.group("currency").upper(),
            match.start("currency"),
            match.end("currency"),
        )
        amount_path = (
            ExtractableFieldPath.SETTLED_AMOUNT
            if confirmation
            else ExtractableFieldPath.SETTLEMENT_AMOUNT
        )
        add_explicit(
            amount_path,
            match.group("amount").replace(",", ""),
            match.start("amount"),
            match.end("amount"),
        )

    for match in re.finditer(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", text):
        prefix = lowered[max(0, match.start() - 24) : match.start()]
        if "trade date" in prefix:
            path = ExtractableFieldPath.TRADE_DATE
        elif "settlement date" in prefix:
            path = ExtractableFieldPath.SETTLEMENT_DATE
        elif confirmation:
            path = ExtractableFieldPath.ACTUAL_SETTLEMENT_DATE
        else:
            path = ExtractableFieldPath.SETTLEMENT_DATE
        add_explicit(path, match.group(), match.start(), match.end())

    placeholder_paths = {
        "ISIN": ExtractableFieldPath.SECURITY_IDENTIFIER,
        "SAFEKEEPING_ACCOUNT": ExtractableFieldPath.SAFEKEEPING_ACCOUNT,
        "SENDER_REFERENCE": ExtractableFieldPath.SENDER_REFERENCE,
        "CLIENT_REFERENCE": ExtractableFieldPath.CLIENT_REFERENCE,
        "RELATED_REFERENCE": ExtractableFieldPath.RELATED_REFERENCE,
        "BUSINESS_REFERENCE": ExtractableFieldPath.SENDER_REFERENCE,
    }
    for issued in sanitised.placeholders.values():
        placeholder_path: ExtractableFieldPath | None = placeholder_paths.get(issued.kind)
        token_start = text.find(issued.token)
        context = lowered[max(0, token_start - 40) : token_start] if token_start >= 0 else ""
        if issued.kind in {"PARTY_ID", "PARTY_NAME", "BIC"}:
            if "delivering" in context:
                placeholder_path = ExtractableFieldPath.DELIVERING_AGENT
            elif "receiving" in context:
                placeholder_path = ExtractableFieldPath.RECEIVING_AGENT
            elif "place of settlement" in context or "settlement place" in context:
                placeholder_path = ExtractableFieldPath.PLACE_OF_SETTLEMENT
        if placeholder_path is None:
            continue
        local[placeholder_path] = GroundedExtractedField(
            field_path=placeholder_path,
            value=issued.token,
            source=ExtractionSource.PLACEHOLDER,
            evidence_start=None,
            evidence_end=None,
            placeholder_id=issued.placeholder_id,
        )

    retained = [
        item
        for item in result.extracted_fields
        if item.field_path == ExtractableFieldPath.REASON_NARRATIVE
        and re.search(r"\b(?:narrative|reason narrative)\b", lowered)
    ]
    result.extracted_fields = [*retained, *local.values()]


def _reconcile_missing_decisions(result: ModelInterpretationResult, text: str) -> None:
    missing: list[MissingDecision] = []
    intent = result.intent
    lowered = text.casefold()
    has_related_reference = any(
        item.field_path == ExtractableFieldPath.RELATED_REFERENCE
        for item in result.extracted_fields
    )
    if intent.lifecycle is None:
        missing.append(MissingDecision.LIFECYCLE)
        if any(token in lowered for token in ("confirm", "status", "pending", "rejected")):
            missing.append(MissingDecision.RESPONSE_TYPE)
    if intent.lifecycle in {None, Lifecycle.INSTRUCTION, Lifecycle.CONFIRMATION}:
        if intent.direction is None:
            missing.append(MissingDecision.DIRECTION)
        if intent.payment_type is None:
            missing.append(MissingDecision.PAYMENT_TYPE)
    if (
        intent.lifecycle in {Lifecycle.CONFIRMATION, Lifecycle.STATUS}
        or re.search(r"\b(?:cancel(?:led|lation)?|reverse|reversal)\b", lowered)
    ) and not has_related_reference:
        missing.append(MissingDecision.ORIGINAL_INSTRUCTION_REFERENCE)
    result.missing_decisions = list(dict.fromkeys(missing))
    if missing or intent.inferred_fields:
        result.requires_clarification = True
    else:
        result.ambiguities = []
        result.requires_clarification = False
