"""The single answer to "what can this platform generate, and what does it need?".

Both the browser UI and the automation API read the catalogue and the format-neutral
:class:`MessageSpec` projection from here, so a message can never be offered in one place
and missing from the other.
"""

from __future__ import annotations

from functools import lru_cache

from app.knowledge.code_lists import code_lists
from app.knowledge.loader import knowledge_repository
from app.knowledge.models import RuleLayer, WorkflowModuleId
from app.profiles.loader import profiles
from app.specifications.registry import specification_registry
from app.studio.capability import (
    CapabilityDimensions,
    capability_summary,
    derive_dimensions,
)
from app.studio.models import (
    BUSINESS_AREA_LABELS,
    MT_OUTPUT_MODES,
    MX_OUTPUT_MODES,
    AllowedValue,
    BusinessArea,
    CatalogueBusinessArea,
    CatalogueEntry,
    CatalogueFormat,
    FieldExample,
    InputKind,
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
# Capability dimensions — derived from what exists, never declared
# --------------------------------------------------------------------------------------


def _profile_configured(message_type: str) -> bool:
    return any(
        profile.requirements_for(message_type) for profile in profiles.list()
    )


def _installed_rule_layers(format_: MessageFormat, message_type: str) -> dict[str, bool]:
    """Which authority layers have a reviewed rule pack installed for this message.

    Measured from the registry, which loads reviewed packs only — so a candidate rule can
    never move a dimension, just as it can never produce a validation finding.
    """
    from app.rule_engine.registry import rule_pack_registry

    layers = rule_pack_registry.layers_for(format_, message_type)
    return {
        "reviewed_business_rules": RuleLayer.BASE_STANDARD in layers,
        "market_practice_configured": RuleLayer.MARKET_PRACTICE in layers,
        "client_rules_configured": RuleLayer.CLIENT_PROFILE in layers,
    }


@lru_cache(maxsize=64)
def capability_dimensions(format_: MessageFormat, message_type: str) -> CapabilityDimensions:
    if format_ is MessageFormat.MT:
        # Hand-authored subsets with configured cross-field and profile rules throughout.
        return derive_dimensions(
            generated_from_schema=False,
            has_business_rules=True,
            profile_configured=_profile_configured(message_type),
            **_installed_rule_layers(format_, message_type),
        )
    spec = mx_registry.get(message_type)
    has_rules = bool(spec.require_one_of) or any(
        item.element.business_path for item in mx_registry.leaves(spec.message_type)
    )
    return derive_dimensions(
        generated_from_schema=spec.source.generated,
        has_business_rules=has_rules,
        profile_configured=_profile_configured(spec.message_type),
        **_installed_rule_layers(format_, spec.message_type),
    )


# --------------------------------------------------------------------------------------
# Format-neutral specification projection
# --------------------------------------------------------------------------------------


@lru_cache(maxsize=64)
def message_spec(format_: MessageFormat, message_type: str) -> MessageSpec:
    if format_ is MessageFormat.MT:
        return _mt_spec(message_type)
    return _mx_spec(message_type)


def _mt_spec(message_type: str) -> MessageSpec:
    specification = specification_registry.get(message_type)
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
                allowed_values=_allowed_values(row.code_list, row.allowed_codes),
                code_list=row.code_list,
                input_kind=InputKind(row.input_kind.value),
                literal_prefix=row.literal_prefix,
                # False everywhere, and stated rather than implied: the composer writes the
                # literal. A client that puts "ISIN " in the value gets it normalised away.
                user_enters_literal_prefix=False,
                identifier_types=row.identifier_types,
                max_length=row.max_length,
                choice_group=row.choice_group,
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
        message_type=specification.message_type,
        version=None,
        name=specification.name,
        business_area=MODULE_TO_AREA[specification.workflow_module],
        scope=specification.scope,
        short_description=specification.short_description,
        namespace=None,
        groups=groups,
        fields=fields,
        output_modes=MT_OUTPUT_MODES,
        authoritative_completeness_known=specification.authoritative_completeness_known,
        source_reference=specification.source.source_reference,
        standards_release=specification.standards_release,
        limitations=MT_LIMITATIONS,
        capability=capability_dimensions(MessageFormat.MT, specification.message_type),
        capability_summary=capability_summary(
            capability_dimensions(MessageFormat.MT, specification.message_type)
        ),
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
                allowed_values=_allowed_values(element.code_list, element.codes),
                code_list=element.code_list,
                input_kind=InputKind.SELECT if element.codes else _mx_input_kind(element),
                examples=[
                    FieldExample(value=example.value, explanation=example.explanation)
                    for example in element.examples
                ],
                common_mistakes=element.common_mistakes,
                condition_explanation=element.condition_explanation
                or _inherited_condition(flat.path, spec),
                business_path=element.business_path,
                xpath=flat.path,
                data_type=(
                    element.data_type.value
                    if element.data_type
                    else (element.restriction.type_name if element.restriction else None)
                ),
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
        short_description=spec.short_description,
        namespace=spec.namespace,
        groups=groups,
        fields=fields,
        output_modes=MX_OUTPUT_MODES,
        authoritative_completeness_known=spec.authoritative_completeness_known,
        source_reference=spec.source.source_reference,
        standards_release=spec.standards_release,
        limitations=spec.limitations,
        capability=capability_dimensions(MessageFormat.MX, spec.message_type),
        capability_summary=capability_summary(
            capability_dimensions(MessageFormat.MX, spec.message_type)
        ),
    )


def _allowed_values(code_list: str | None, codes: list[str]) -> list[AllowedValue]:
    """Codes with their words. A field with codes but no named list still gets a select."""
    return [
        AllowedValue(code=item.code, label=item.label, description=item.description)
        for item in code_lists.describe(code_list, codes)
    ]


def _mx_input_kind(element) -> InputKind:  # type: ignore[no-untyped-def]
    """The control for an ISO 20022 leaf, from its representation class."""
    if element.data_type is None and element.restriction is not None:
        from app.studio.mx.models import MxRestrictionBase

        return {
            MxRestrictionBase.DATE: InputKind.DATE,
            MxRestrictionBase.DATE_TIME: InputKind.DATE,
            MxRestrictionBase.DECIMAL: InputKind.QUANTITY,
            MxRestrictionBase.BOOLEAN: InputKind.INDICATOR,
        }.get(element.restriction.base, InputKind.TEXT)
    data_type = element.data_type.value if element.data_type else ""
    if data_type.startswith("ISIN"):
        return InputKind.IDENTIFIER
    if data_type.startswith("AnyBIC"):
        return InputKind.PARTY_BIC
    if data_type == "ISODate":
        return InputKind.DATE
    if data_type in {"ActiveCurrencyAndAmount", "RestrictedFINActiveCurrencyAndAmount"}:
        return InputKind.AMOUNT
    if data_type in {"DecimalNumber", "RestrictedFINDecimalNumber"}:
        return InputKind.QUANTITY
    if data_type == "YesNoIndicator":
        return InputKind.INDICATOR
    return InputKind.TEXT


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
        short_description=spec.short_description or spec.scope,
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
        capability=spec.capability,
        capability_summary=spec.capability_summary,
    )


def build_catalogue() -> StudioCatalogue:
    from app.studio.samples import available_variants

    entries: list[CatalogueEntry] = []
    for mt_spec in specification_registry.list():
        spec = message_spec(MessageFormat.MT, mt_spec.message_type)
        entries.append(
            _entry(spec, available_variants(MessageFormat.MT, mt_spec.message_type))
        )
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
        return specification_registry.known(message_type)
    return mx_registry.known(message_type)


__all__ = [
    "MxDataType",
    "build_catalogue",
    "known_message_type",
    "message_spec",
    "resolve_format",
]
