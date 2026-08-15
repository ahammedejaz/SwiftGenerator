from copy import deepcopy
from enum import StrEnum
from functools import lru_cache
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    Direction,
    Lifecycle,
    MessageFunction,
    PaymentType,
    ResponseAction,
    TransactionType,
)

PROMPT_VERSION = "settlement-intent-v2"
SCHEMA_VERSION = "settlement-interpretation-v2"
SCHEMA_NAME = "securities_settlement_interpretation"


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class AgentModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        use_enum_values=False,
    )


class ExtractionSource(StrEnum):
    EXPLICIT = "EXPLICIT"
    PLACEHOLDER = "PLACEHOLDER"


class IntentField(StrEnum):
    LIFECYCLE = "lifecycle"
    DIRECTION = "direction"
    PAYMENT_TYPE = "paymentType"
    TRANSACTION_TYPE = "transactionType"
    FUNCTION = "function"
    RESPONSE_ACTION = "responseAction"


class MissingDecision(StrEnum):
    LIFECYCLE = "lifecycle"
    DIRECTION = "direction"
    PAYMENT_TYPE = "paymentType"
    ORIGINAL_INSTRUCTION_REFERENCE = "originalInstructionReference"
    RESPONSE_TYPE = "confirmationOrStatusType"


class ExtractableFieldPath(StrEnum):
    SENDER_REFERENCE = "senderReference"
    RELATED_REFERENCE = "relatedReference"
    CLIENT_REFERENCE = "clientReference"
    TRADE_DATE = "trade.tradeDate"
    SETTLEMENT_DATE = "trade.settlementDate"
    SECURITY_IDENTIFIER = "security.identifier"
    SECURITY_QUANTITY = "security.quantity"
    SAFEKEEPING_ACCOUNT = "account.safekeepingAccount"
    SETTLEMENT_CURRENCY = "settlement.currency"
    SETTLEMENT_AMOUNT = "settlement.amount"
    PLACE_OF_SETTLEMENT = "settlement.placeOfSettlement"
    DELIVERING_AGENT = "settlement.deliveringAgent"
    RECEIVING_AGENT = "settlement.receivingAgent"
    ACTUAL_SETTLEMENT_DATE = "confirmation.actualSettlementDate"
    SETTLED_QUANTITY = "confirmation.settledQuantity"
    SETTLED_AMOUNT = "confirmation.settledAmount"
    REASON_NARRATIVE = "status.narrative"


class ModelIntent(AgentModel):
    lifecycle: Lifecycle | None
    direction: Direction | None
    payment_type: PaymentType | None
    transaction_type: TransactionType | None
    function: MessageFunction | None
    response_action: ResponseAction | None
    inferred_fields: list[IntentField]


class GroundedExtractedField(AgentModel):
    field_path: ExtractableFieldPath
    value: str = Field(min_length=1, max_length=256)
    source: ExtractionSource
    evidence_start: int | None
    evidence_end: int | None
    placeholder_id: str | None


class ModelInterpretationResult(AgentModel):
    intent: ModelIntent
    extracted_fields: list[GroundedExtractedField] = Field(max_length=24)
    ambiguities: list[str] = Field(max_length=12)
    missing_decisions: list[MissingDecision] = Field(max_length=12)
    interpretation_summary: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    requires_clarification: bool


def strict_interpretation_schema() -> dict[str, object]:
    """Return a provider-compatible copy of the authoritative response schema."""
    return deepcopy(_normalised_interpretation_schema())


class ProviderSchemaError(ValueError):
    """Raised when the application schema cannot be represented safely for the provider."""


@lru_cache(maxsize=1)
def _normalised_interpretation_schema() -> dict[str, object]:
    source = ModelInterpretationResult.model_json_schema(by_alias=True)
    normalised = normalise_provider_schema(source)
    if not isinstance(normalised, dict):
        raise ProviderSchemaError("#: schema normalisation did not produce an object")
    lint_provider_schema(normalised)
    return cast(dict[str, object], normalised)


def normalise_provider_schema(value: Any, path: str = "#") -> Any:
    if isinstance(value, list):
        return [
            normalise_provider_schema(item, f"{path}/{index}") for index, item in enumerate(value)
        ]
    if not isinstance(value, dict):
        return value

    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"default", "title"}:
            continue
        result[key] = normalise_provider_schema(item, f"{path}/{key}")

    properties = result.get("properties")
    if properties is not None:
        if not isinstance(properties, dict):
            raise ProviderSchemaError(f"{path}: object properties must be a mapping")
        result["type"] = "object"
        result["additionalProperties"] = False
        result["required"] = list(properties)

    additional = result.get("additionalProperties")
    if additional not in {None, False}:
        raise ProviderSchemaError(f"{path}: arbitrary property bags are not supported")
    return result


def lint_provider_schema(schema: dict[str, object]) -> None:
    """Fail closed when a schema violates the supported strict-output subset."""
    if schema.get("type") != "object":
        raise ProviderSchemaError("#: the root schema must be an object")
    if "anyOf" in schema:
        raise ProviderSchemaError("#: root anyOf is not supported")

    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise ProviderSchemaError("#/$defs: definitions must be a mapping")

    expected_enums = {
        "Direction": {item.value for item in Direction},
        "ExtractionSource": {item.value for item in ExtractionSource},
        "ExtractableFieldPath": {item.value for item in ExtractableFieldPath},
        "IntentField": {item.value for item in IntentField},
        "Lifecycle": {item.value for item in Lifecycle},
        "MessageFunction": {item.value for item in MessageFunction},
        "MissingDecision": {item.value for item in MissingDecision},
        "PaymentType": {item.value for item in PaymentType},
        "ResponseAction": {item.value for item in ResponseAction},
        "TransactionType": {item.value for item in TransactionType},
    }
    forbidden_properties = {"messageType", "rawMessage", "rawMtMessage", "tags", "sequences"}

    def resolve_reference(reference: str, path: str) -> None:
        prefix = "#/$defs/"
        if not reference.startswith(prefix) or reference[len(prefix) :] not in definitions:
            raise ProviderSchemaError(f"{path}: unresolved or external reference")

    def visit(node: Any, path: str) -> None:
        if isinstance(node, list):
            for index, item in enumerate(node):
                visit(item, f"{path}/{index}")
            return
        if not isinstance(node, dict):
            return
        if "default" in node:
            raise ProviderSchemaError(f"{path}: defaults are not supported")
        reference = node.get("$ref")
        if reference is not None:
            if not isinstance(reference, str):
                raise ProviderSchemaError(f"{path}/$ref: reference must be a string")
            resolve_reference(reference, f"{path}/$ref")
        properties = node.get("properties")
        if node.get("type") == "object" or properties is not None:
            if not isinstance(properties, dict) or not properties:
                raise ProviderSchemaError(f"{path}: unconstrained objects are not supported")
            if node.get("additionalProperties") is not False:
                raise ProviderSchemaError(f"{path}: additionalProperties must be false")
            required = node.get("required")
            if not isinstance(required, list) or set(required) != set(properties):
                raise ProviderSchemaError(f"{path}: every property must be required")
            if forbidden_properties.intersection(properties):
                raise ProviderSchemaError(f"{path}: authoritative MT output fields are forbidden")
        any_of = node.get("anyOf")
        if any_of is not None:
            if path == "#" or not isinstance(any_of, list):
                raise ProviderSchemaError(f"{path}: unsupported anyOf")
            null_branches = sum(
                isinstance(branch, dict) and branch.get("type") == "null" for branch in any_of
            )
            if null_branches != 1:
                raise ProviderSchemaError(f"{path}: optional values must use one null branch")
        additional = node.get("additionalProperties")
        if additional not in {None, False}:
            raise ProviderSchemaError(f"{path}: arbitrary property bags are not supported")
        for key, item in node.items():
            visit(item, f"{path}/{key}")

    visit(schema, "#")
    for name, expected in expected_enums.items():
        definition = definitions.get(name)
        if not isinstance(definition, dict) or set(definition.get("enum", [])) != expected:
            raise ProviderSchemaError(f"#/$defs/{name}: enum differs from the application model")
