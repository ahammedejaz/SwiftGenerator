from copy import deepcopy
from typing import Any

import pytest

from app.agents.schemas import (
    ModelInterpretationResult,
    ProviderSchemaError,
    lint_provider_schema,
    normalise_provider_schema,
    strict_interpretation_schema,
)


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_production_schema_is_strict_recursively_and_has_no_defaults() -> None:
    schema = strict_interpretation_schema()

    assert schema["type"] == "object"
    assert "anyOf" not in schema
    assert all("default" not in node for node in _walk(schema) if isinstance(node, dict))
    for node in _walk(schema):
        if isinstance(node, dict) and (node.get("type") == "object" or "properties" in node):
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])


def test_optional_values_are_required_nullable_fields() -> None:
    schema = strict_interpretation_schema()
    intent = schema["$defs"]["ModelIntent"]

    assert "lifecycle" in intent["required"]
    lifecycle = intent["properties"]["lifecycle"]
    assert sum(branch.get("type") == "null" for branch in lifecycle["anyOf"]) == 1


def test_schema_normalisation_removes_metadata_and_requires_all_properties() -> None:
    raw = {
        "type": "object",
        "title": "Unsafe metadata",
        "properties": {
            "optional": {
                "default": None,
                "anyOf": [{"type": "string"}, {"type": "null"}],
            }
        },
    }

    normalised = normalise_provider_schema(raw)

    assert "title" not in normalised
    assert "default" not in normalised["properties"]["optional"]
    assert normalised["additionalProperties"] is False
    assert normalised["required"] == ["optional"]


def test_all_local_refs_resolve_and_application_enums_are_unchanged() -> None:
    lint_provider_schema(strict_interpretation_schema())

    broken_reference = deepcopy(strict_interpretation_schema())
    broken_reference["properties"]["intent"] = {"$ref": "#/$defs/DoesNotExist"}
    with pytest.raises(ProviderSchemaError, match="unresolved"):
        lint_provider_schema(broken_reference)

    broken_enum = deepcopy(strict_interpretation_schema())
    broken_enum["$defs"]["Direction"]["enum"].append("INVENTED")
    with pytest.raises(ProviderSchemaError, match="enum differs"):
        lint_provider_schema(broken_enum)


def test_lint_rejects_root_union_property_bags_and_raw_output_fields() -> None:
    root_union = deepcopy(strict_interpretation_schema())
    root_union["anyOf"] = [{"type": "object"}, {"type": "null"}]
    with pytest.raises(ProviderSchemaError, match="root anyOf"):
        lint_provider_schema(root_union)

    arbitrary = ModelInterpretationResult.model_json_schema(by_alias=True)
    arbitrary["properties"]["intent"] = {"type": "object", "additionalProperties": True}
    with pytest.raises(ProviderSchemaError, match="arbitrary property bags"):
        normalise_provider_schema(arbitrary)

    raw_output = deepcopy(strict_interpretation_schema())
    raw_output["properties"]["rawMessage"] = {"type": "string"}
    raw_output["required"].append("rawMessage")
    with pytest.raises(ProviderSchemaError, match="authoritative MT output"):
        lint_provider_schema(raw_output)
