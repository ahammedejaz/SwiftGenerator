"""Closed JSON schemas for every authoring call.

``additionalProperties: false`` throughout, and every identifier the model may emit — a
message, a field id, a code — is an ``enum`` built from the catalogue or the Structure Pack
at call time. A model cannot name a field the structure lacks because the schema has no
room for it.
"""

from __future__ import annotations

from typing import Any

MAX_ENUM = 4_000
MAX_VALUE_LENGTH = 2_000


def _string(max_length: int = 500) -> dict[str, Any]:
    return {"type": "string", "maxLength": max_length}


#: Providers cap the number of enum values a strict schema may carry. Above it the field
#: stays a plain string and the deterministic check after the call does the rejecting —
#: the model gains no authority either way, it just loses the early constraint.
MAX_ENUM_VALUES = 900


def _enum(values: list[str]) -> dict[str, Any]:
    unique = list(dict.fromkeys(values))[:MAX_ENUM]
    if len(unique) > MAX_ENUM_VALUES:
        return {"type": "string", "maxLength": 400}
    return {"type": "string", "enum": unique}


def identify_schema(candidates: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["candidates", "explanation", "missingInformation", "confidence"],
        "properties": {
            "candidates": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["messageKey", "confidence", "reason"],
                    "properties": {
                        "messageKey": _enum(candidates or ["NONE"]),
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": _string(400),
                    },
                },
            },
            "explanation": _string(800),
            "missingInformation": {"type": "array", "maxItems": 10, "items": _string(200)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def canonical_values_schema(
    field_ids: list[str], *, allow_questions: bool = True
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "scenario": _string(600),
        "values": {
            "type": "array",
            "maxItems": 500,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fieldId", "occurrence", "value"],
                "properties": {
                    "fieldId": _enum(field_ids or ["NONE"]),
                    "occurrence": {"type": "integer", "minimum": 1, "maximum": 100},
                    "value": _string(MAX_VALUE_LENGTH),
                },
            },
        },
        "missingFields": {"type": "array", "maxItems": 50, "items": _enum(field_ids or ["NONE"])},
        "notes": {"type": "array", "maxItems": 10, "items": _string(300)},
    }
    required = ["scenario", "values", "missingFields", "notes"]
    if allow_questions:
        properties["questions"] = {"type": "array", "maxItems": 10, "items": _string(300)}
        required.append("questions")
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def scenarios_schema(field_ids: list[str], *, count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["scenarios"],
        "properties": {
            "scenarios": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(1, count),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "values"],
                    "properties": {
                        "title": _string(200),
                        "values": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["fieldId", "occurrence", "value"],
                                "properties": {
                                    "fieldId": _enum(field_ids or ["NONE"]),
                                    "occurrence": {"type": "integer", "minimum": 1, "maximum": 100},
                                    "value": _string(MAX_VALUE_LENGTH),
                                },
                            },
                        },
                    },
                },
            }
        },
    }


def negative_schema(field_ids: list[str], rule_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["mutations"],
        "properties": {
            "mutations": {
                "type": "array",
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["expectedRuleId", "title", "values"],
                    "properties": {
                        "expectedRuleId": _enum(rule_ids or ["NONE"]),
                        "title": _string(200),
                        "values": {
                            "type": "array",
                            "maxItems": 500,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["fieldId", "occurrence", "value"],
                                "properties": {
                                    "fieldId": _enum(field_ids or ["NONE"]),
                                    "occurrence": {"type": "integer", "minimum": 1, "maximum": 100},
                                    "value": _string(MAX_VALUE_LENGTH),
                                },
                            },
                        },
                    },
                },
            }
        },
    }


def presentation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "displayLabel",
            "businessMeaning",
            "businessQuestion",
            "example",
            "whyNeeded",
            "commonMistake",
            "citations",
        ],
        "properties": {
            "displayLabel": _string(80),
            "businessMeaning": _string(400),
            "businessQuestion": _string(200),
            "example": _string(100),
            "whyNeeded": _string(300),
            "commonMistake": _string(300),
            "citations": {"type": "array", "maxItems": 8, "items": _string(120)},
        },
    }


def answer_schema(segment_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "supported", "citations", "caveats"],
        "properties": {
            "answer": _string(1_500),
            "supported": {
                "type": "string",
                "enum": ["SUPPORTED", "PARTIAL", "UNSUPPORTED_BY_EVIDENCE"],
            },
            "citations": {
                "type": "array",
                "maxItems": 12,
                "items": _enum(segment_ids or ["NONE"]),
            },
            "caveats": {"type": "array", "maxItems": 6, "items": _string(300)},
        },
    }


def comparison_schema(segment_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "differences", "citations"],
        "properties": {
            "summary": _string(1_200),
            "differences": {
                "type": "array",
                "maxItems": 30,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["area", "change", "citations"],
                    "properties": {
                        "area": _string(120),
                        "change": _string(400),
                        "citations": {
                            "type": "array",
                            "maxItems": 6,
                            "items": _enum(segment_ids or ["NONE"]),
                        },
                    },
                },
            },
            "citations": {"type": "array", "maxItems": 20, "items": _enum(segment_ids or ["NONE"])},
        },
    }
