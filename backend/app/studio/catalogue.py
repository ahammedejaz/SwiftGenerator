"""The single answer to "what can this platform generate, and what does it need?".

Both the browser UI and the automation API read the catalogue and the format-neutral
:class:`MessageSpec` projection from here, so a message can never be offered in one place
and missing from the other.
"""

from __future__ import annotations

from functools import lru_cache

from app.domain.enums import MessageType
from app.knowledge.loader import knowledge_repository
from app.knowledge.models import WorkflowModuleId
from app.profiles.loader import profiles
from app.specifications.registry import specification_registry
from app.studio.models import (
    BUSINESS_AREA_LABELS,
    MT_OUTPUT_MODES,
    MX_OUTPUT_MODES,
    BusinessArea,
    CatalogueBusinessArea,
    CatalogueEntry,
    CatalogueFormat,
    FieldExample,
    MessageFormat,
    MessageSpec,
    Presence,
    SampleVariant,
    SpecField,
    SpecGroup,
    StudioCatalogue,
)
from app.studio.mx.models import MxDataType
from app.studio.mx.registry import mx_registry

MODULE_TO_AREA: dict[WorkflowModuleId, BusinessArea] = {
    WorkflowModuleId.SETTLEMENT: BusinessArea.SECURITIES_SETTLEMENT,
    WorkflowModuleId.SETTLEMENT_COMMAND: BusinessArea.SETTLEMENT_COMMANDS,
    WorkflowModuleId.PENALTIES: BusinessArea.PENALTIES,
    WorkflowModuleId.CORPORATE_ACTIONS: BusinessArea.CORPORATE_ACTIONS,
}

#: Plain-English one-liners so a tester who has never seen ISO 15022 can still choose.
MT_DESCRIPTIONS: dict[MessageType, str] = {
    MessageType.MT530: "Change the processing priority of an existing settlement instruction.",
    MessageType.MT537: "Report settlement-discipline penalties on failed transactions.",
    MessageType.MT540: "Instruct the receipt of securities free of payment.",
    MessageType.MT541: "Instruct the receipt of securities against a cash payment.",
    MessageType.MT542: "Instruct the delivery of securities free of payment.",
    MessageType.MT543: "Instruct the delivery of securities against a cash payment.",
    MessageType.MT544: "Confirm that securities were received free of payment.",
    MessageType.MT545: "Confirm that securities were received against a cash payment.",
    MessageType.MT546: "Confirm that securities were delivered free of payment.",
    MessageType.MT547: "Confirm that securities were delivered against a cash payment.",
    MessageType.MT548: "Advise the status of a settlement instruction, with the reason.",
    MessageType.MT564: "Notify the account owner of a corporate action event and its options.",
    MessageType.MT565: "Instruct an election on a corporate action option.",
    MessageType.MT566: "Confirm the outcome of a corporate action election.",
    MessageType.MT567: "Advise the status of a corporate action instruction.",
    MessageType.MT568: "Send supporting narrative for a corporate action event.",
}

FORMAT_DESCRIPTIONS: dict[MessageFormat, str] = {
    MessageFormat.MT: "Traditional Swift FIN messages built from tags and sequences (ISO 15022).",
    MessageFormat.MX: "ISO 20022 XML messages built from a Business Application Header and a "
    "Document.",
}

MT_LIMITATIONS = [
    "Coverage is the repository's configured subset of the format, not the complete "
    "authoritative format definition.",
    "Network validation rules and market or institution rule packs require an authorised import.",
]


# --------------------------------------------------------------------------------------
# Format-neutral specification projection
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=64)
def message_spec(format_: MessageFormat, message_type: str) -> MessageSpec:
    if format_ is MessageFormat.MT:
        return _mt_spec(message_type)
    return _mx_spec(message_type)


def _mt_spec(message_type: str) -> MessageSpec:
    specification = specification_registry.get(MessageType(message_type.upper()))
    groups = [
        SpecGroup(
            id=sequence.path,
            label=f"{sequence.code} — {_sequence_label(sequence.code)}",
            description=f"Sequence {sequence.path} ({sequence.code}).",
            order=sequence.order,
            repeatable=sequence.max_occurs > 1,
            max_occurs=sequence.max_occurs,
            parent_id=sequence.parent_path,
        )
        for sequence in specification.sequences
    ]
    by_path = {sequence.path: sequence for sequence in specification.sequences}
    fields: list[SpecField] = []
    for row in specification.fields:
        sequence = by_path[row.sequence_path]
        knowledge = _knowledge(row.knowledge_id)
        fields.append(
            SpecField(
                id=row.row_id,
                format=MessageFormat.MT,
                group_id=row.sequence_path,
                group_label=f"{sequence.code} — {_sequence_label(sequence.code)}",
                group_order=sequence.order,
                order=row.row_number,
                presence=Presence(row.presence.value),
                repeatable=row.repeatable,
                max_occurs=row.max_occurs,
                display_name=row.business_name,
                business_meaning=knowledge.business_meaning if knowledge else row.technical_name,
                technical_meaning=row.technical_name,
                why_used=knowledge.why_used if knowledge else "",
                business_question=knowledge.business_question if knowledge else "",
                missing_impact=knowledge.missing_impact if knowledge else None,
                format_explanation=row.format,
                allowed_codes=row.allowed_codes,
                examples=[
                    FieldExample(value=example.value, explanation=example.explanation)
                    for example in (knowledge.example_values if knowledge else [])
                ],
                common_mistakes=knowledge.common_mistakes if knowledge else [],
                depends_on=knowledge.depends_on if knowledge else [],
                condition_explanation=row.condition_explanation,
                business_path=row.business_path,
                sequence=row.sequence_path,
                sequence_code=row.sequence_code,
                tag=row.tag,
                qualifier=row.qualifier,
                option=row.option,
                source_reference=row.source.source_reference,
                standards_release=row.source.standards_release,
            )
        )
    return MessageSpec(
        format=MessageFormat.MT,
        message_type=specification.message_type.value,
        version=None,
        name=specification.name,
        business_area=MODULE_TO_AREA[specification.workflow_module],
        scope=specification.scope,
        namespace=None,
        groups=groups,
        fields=fields,
        output_modes=MT_OUTPUT_MODES,
        authoritative_completeness_known=specification.authoritative_completeness_known,
        source_reference=specification.source.source_reference,
        standards_release=specification.standards_release,
        limitations=MT_LIMITATIONS,
    )


def _mx_spec(message_type: str) -> MessageSpec:
    spec = mx_registry.get(message_type)
    root = f"/{spec.document_element}/{spec.message_root}"
    groups: list[SpecGroup] = []
    fields: list[SpecField] = []
    seen_groups: set[str] = set()

    for flat in mx_registry.flat(spec.message_type):
        element = flat.element
        if not element.is_leaf:
            continue
        group_path = flat.parent_path or root
        # Group by the nearest ancestor directly under the message root, so the UI shows
        # a handful of meaningful blocks rather than one group per nesting level.
        relative = group_path[len(root) :].strip("/")
        top = relative.split("/")[0] if relative else ""
        group_id = f"{root}/{top}" if top else root
        if group_id not in seen_groups:
            seen_groups.add(group_id)
            top_element = next(
                (item for item in spec.structure if item.name == top), None
            )
            groups.append(
                SpecGroup(
                    id=group_id,
                    label=top_element.display_name if top_element else spec.message_root,
                    description=(
                        top_element.business_meaning
                        if top_element and top_element.business_meaning
                        else "Top-level elements of the message."
                    ),
                    order=len(groups) + 1,
                    repeatable=bool(top_element and top_element.max_occurs > 1),
                    max_occurs=top_element.max_occurs if top_element else 1,
                )
            )
        group = next(item for item in groups if item.id == group_id)
        presence = element.presence
        # A mandatory leaf under an optional container is conditional from the user's
        # point of view: it is only required once that container is used.
        if presence is Presence.MANDATORY and not flat.mandatory_chain:
            presence = Presence.CONDITIONAL
        fields.append(
            SpecField(
                id=flat.path,
                format=MessageFormat.MX,
                group_id=group_id,
                group_label=group.label,
                group_order=group.order,
                order=flat.order,
                presence=presence,
                repeatable=element.max_occurs > 1,
                max_occurs=element.max_occurs,
                display_name=element.display_name,
                business_meaning=element.business_meaning,
                technical_meaning=element.technical_meaning,
                why_used=element.why_used,
                business_question=element.business_question,
                format_explanation=element.format_text(),
                allowed_codes=element.codes,
                examples=[
                    FieldExample(value=example.value, explanation=example.explanation)
                    for example in element.examples
                ],
                common_mistakes=element.common_mistakes,
                condition_explanation=element.condition_explanation
                or _inherited_condition(flat.path, spec),
                business_path=element.business_path,
                xpath=flat.path,
                data_type=element.data_type.value if element.data_type else None,
                choice_group=flat.choice_branch or flat.choice_group,
                source_reference=spec.source.source_reference,
                standards_release=spec.standards_release,
            )
        )
    return MessageSpec(
        format=MessageFormat.MX,
        message_type=spec.message_type,
        version=spec.version,
        name=spec.name,
        business_area=spec.business_area,
        scope=spec.short_description,
        namespace=spec.namespace,
        groups=groups,
        fields=fields,
        output_modes=MX_OUTPUT_MODES,
        authoritative_completeness_known=spec.authoritative_completeness_known,
        source_reference=spec.source.source_reference,
        standards_release=spec.standards_release,
        limitations=spec.limitations,
    )


def _inherited_condition(path: str, spec) -> str | None:  # type: ignore[no-untyped-def]
    """Surface the nearest ancestor's condition so a leaf explains when it applies."""
    by_path = mx_registry.by_path(spec.message_type)
    parts = path.split("/")
    for depth in range(len(parts) - 1, 2, -1):
        ancestor = by_path.get("/".join(parts[:depth]))
        if ancestor and ancestor.element.condition_explanation:
            return ancestor.element.condition_explanation
    return None


SEQUENCE_LABELS = {
    "GENL": "General Information",
    "TRADDET": "Trade Details",
    "FIAC": "Financial Instrument and Account",
    "SETDET": "Settlement Details",
    "CONFDET": "Confirmation Details",
    "LINK": "Linkages",
    "STAT": "Status",
    "REQD": "Requested Details",
    "PENA": "Penalties",
    "PENACUR": "Penalties by Currency",
    "PENACOUNT": "Penalties by Counterparty",
    "PENDET": "Penalty Details",
    "RELTRAN": "Related Transaction",
    "USECU": "Underlying Securities",
    "ACCTINFO": "Account Information",
    "CADETL": "Corporate Action Details",
    "CAOPTN": "Corporate Action Options",
    "CAINST": "Corporate Action Instruction",
    "CACONF": "Corporate Action Confirmation",
    "ADDINFO": "Additional Information",
}


def _sequence_label(code: str) -> str:
    return SEQUENCE_LABELS.get(code, code.title())


def _knowledge(knowledge_id: str):  # type: ignore[no-untyped-def]
    try:
        return knowledge_repository.get(knowledge_id)
    except KeyError:
        return None


# --------------------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------------------


def _entry(spec: MessageSpec, variants: tuple[SampleVariant, ...]) -> CatalogueEntry:
    return CatalogueEntry(
        format=spec.format,
        message_type=spec.message_type,
        version=spec.version,
        name=spec.name,
        short_description=(
            MT_DESCRIPTIONS.get(MessageType(spec.message_type), spec.scope)
            if spec.format is MessageFormat.MT
            else spec.scope
        ),
        business_area=spec.business_area,
        business_area_label=BUSINESS_AREA_LABELS[spec.business_area],
        generatable=True,
        output_modes=spec.output_modes,
        field_count=len(spec.fields),
        mandatory_field_count=sum(
            1 for item in spec.fields if item.presence is Presence.MANDATORY
        ),
        sample_variants=list(variants),
        authoritative_completeness_known=spec.authoritative_completeness_known,
        source_reference=spec.source_reference,
        limitations=spec.limitations,
    )


def build_catalogue() -> StudioCatalogue:
    from app.studio.samples import available_variants

    entries: list[CatalogueEntry] = []
    for message_type in sorted(MessageType, key=lambda item: item.value):
        spec = message_spec(MessageFormat.MT, message_type.value)
        entries.append(_entry(spec, available_variants(MessageFormat.MT, message_type.value)))
    for mx_spec in mx_registry.all_specs():
        spec = message_spec(MessageFormat.MX, mx_spec.message_type)
        entries.append(_entry(spec, available_variants(MessageFormat.MX, mx_spec.message_type)))

    formats: list[CatalogueFormat] = []
    for format_ in (MessageFormat.MT, MessageFormat.MX):
        subset = [entry for entry in entries if entry.format is format_]
        areas: list[CatalogueBusinessArea] = []
        for area in BusinessArea:
            count = sum(1 for entry in subset if entry.business_area is area)
            if count:
                areas.append(
                    CatalogueBusinessArea(
                        id=area, label=BUSINESS_AREA_LABELS[area], message_count=count
                    )
                )
        formats.append(
            CatalogueFormat(
                id=format_,
                label="MT (ISO 15022)" if format_ is MessageFormat.MT else "MX (ISO 20022)",
                description=FORMAT_DESCRIPTIONS[format_],
                business_areas=areas,
                message_count=len(subset),
            )
        )
    return StudioCatalogue(
        formats=formats,
        messages=entries,
        profiles=[profile.profile_id for profile in profiles.list()],
        default_profile_id="BASE_DEMO_V1",
    )


def resolve_format(message_type: str) -> MessageFormat:
    """Infer the format from a message type, so callers may omit it."""
    candidate = message_type.strip().upper()
    if candidate.startswith("MT"):
        return MessageFormat.MT
    if mx_registry.known(message_type):
        return MessageFormat.MX
    raise KeyError(f"Unknown message type: {message_type}")


def known_message_type(format_: MessageFormat, message_type: str) -> bool:
    if format_ is MessageFormat.MT:
        try:
            MessageType(message_type.strip().upper())
        except ValueError:
            return False
        return True
    return mx_registry.known(message_type)


__all__ = [
    "MxDataType",
    "build_catalogue",
    "known_message_type",
    "message_spec",
    "resolve_format",
]
