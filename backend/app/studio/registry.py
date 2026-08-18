"""Format-neutral message-definition registry: discovery metadata for every message.

This is the one place that answers "which message definitions are installed?" without
caring which format they are. It is deliberately *catalogue* metadata only — rendering
stays with the MT and MX adapters, which never merge — and it is a projection over the
two format registries rather than a third store, so it cannot disagree with them.

A message definition exists because a specification pack is installed: a manifest entry
plus knowledge records for MT, a YAML tree for MX. Nothing here consults a closed enum.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.specifications.registry import specification_registry
from app.studio.capability import CapabilityDimensions
from app.studio.models import MessageFormat
from app.studio.mx.registry import mx_registry


@dataclass(frozen=True)
class MessageDefinition:
    """Identity and standing of one installed message definition."""

    message_id: str
    format: MessageFormat
    #: The grouping a standards catalogue would use: the business-area prefix for MX
    #: (``sese``), the category for MT (``MT5``).
    family: str
    #: The full versioned identity where the format has one (``sese.023.001.11``).
    version: str | None
    name: str
    structure_source: str
    capability: CapabilityDimensions


def _mt_definitions() -> list[MessageDefinition]:
    from app.studio.catalogue import capability_dimensions

    return [
        MessageDefinition(
            message_id=spec.message_type,
            format=MessageFormat.MT,
            family=spec.message_type[:3],
            version=None,
            name=spec.name,
            structure_source=spec.source.source_reference,
            capability=capability_dimensions(MessageFormat.MT, spec.message_type),
        )
        for spec in specification_registry.list()
    ]


def _mx_definitions() -> list[MessageDefinition]:
    from app.studio.catalogue import capability_dimensions

    return [
        MessageDefinition(
            message_id=spec.message_type,
            format=MessageFormat.MX,
            family=spec.message_type.split(".")[0],
            version=spec.version,
            name=spec.name,
            structure_source=spec.source.source_reference,
            capability=capability_dimensions(MessageFormat.MX, spec.message_type),
        )
        for spec in mx_registry.all_specs()
    ]


def all_definitions() -> list[MessageDefinition]:
    return [*_mt_definitions(), *_mx_definitions()]


def get(message_id: str) -> MessageDefinition:
    candidate = message_id.strip()
    for definition in all_definitions():
        if definition.message_id.lower() == candidate.lower():
            return definition
    raise KeyError(f"No installed message definition: {message_id}")


def by_format(format_: MessageFormat) -> list[MessageDefinition]:
    return [item for item in all_definitions() if item.format is format_]


def by_family(family: str) -> list[MessageDefinition]:
    return [
        item for item in all_definitions() if item.family.lower() == family.strip().lower()
    ]


def capabilities(message_id: str) -> CapabilityDimensions:
    return get(message_id).capability
