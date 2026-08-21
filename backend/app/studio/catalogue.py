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
from app.specifications.models import MessageSpecification
from app.specifications.registry import specification_registry
from app.studio.capability import (
    BusinessRuleStatus,
    CapabilityDimensions,
    ExternalValidationStatus,
    OverlayStatus,
    StructureStatus,
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
    Lane,
    MessageFormat,
    MessageSpec,
    Presence,
    Readiness,
    SampleVariant,
    SpecField,
    SpecGroup,
    StudioCatalogue,
)
from app.studio.mx.models import MxDataType, MxMessageSpec
from app.studio.mx.registry import MxRegistry, mx_registry

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


@lru_cache(maxsize=256)
def message_spec(
    format_: MessageFormat,
    message_type: str,
    lane: Lane = Lane.CONFIGURED,
    release: str | None = None,
) -> MessageSpec:
    """The format-neutral projection of one message in one lane.

    The configured lane reads the registries this process was started with. The
    knowledge-preview lane reads the local Structure Packs the knowledge sync compiled —
    a separate registry, consulted only when a caller names the lane.
    """
    if lane is Lane.KNOWLEDGE_PREVIEW:
        from app.knowledge_base.preview import preview_registries

        registries = preview_registries()
        if format_ is MessageFormat.MT:
            return _mt_spec_from(registries.resolve_mt(message_type, release))
        spec = registries.resolve_mx(message_type)
        assert registries.mx_registry is not None
        return _mx_spec_from(spec, registries.mx_registry)
    if format_ is MessageFormat.MT:
        return _mt_spec_from(specification_registry.get(message_type))
    return _mx_spec_from(mx_registry.get(message_type), mx_registry)


def _mt_spec_from(specification: MessageSpecification) -> MessageSpec:
    preview = specification.lane == Lane.KNOWLEDGE_PREVIEW.value
    groups = [
        SpecGroup(
            id=sequence.path,
            label=f"{sequence.code} — {_sequence_label(sequence.code)}"
            if sequence.bracketed
            else f"{sequence.path} — {_sequence_label(sequence.code)}",
            description=f"Sequence {sequence.path} ({sequence.code}).",
            order=sequence.order,
            repeatable=sequence.max_occurs > 1,
            max_occurs=sequence.max_occurs,
            parent_id=sequence.parent_path,
            min_occurs=sequence.min_occurs,
        )
        for sequence in specification.sequences
    ]
    by_path = {sequence.path: sequence for sequence in specification.sequences}
    fields: list[SpecField] = []
    for row in specification.fields:
        if row.value_less:
            continue  # written by the composer; never a form control
        sequence = by_path[row.sequence_path]
        knowledge = None if preview else _knowledge(row.knowledge_id)
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
    if preview:
        capability = derive_dimensions(
            generated_from_schema=True,
            has_business_rules=False,
            profile_configured=False,
            reviewed_business_rules=False,
            market_practice_configured=False,
            client_rules_configured=False,
        )
    else:
        capability = capability_dimensions(MessageFormat.MT, specification.message_type)
    return MessageSpec(
        format=MessageFormat.MT,
        message_type=specification.message_type,
        version=None,
        name=specification.name,
        business_area=_area_for(specification),
        scope=specification.scope,
        short_description=specification.short_description,
        namespace=None,
        groups=groups,
        fields=fields,
        output_modes=MT_OUTPUT_MODES,
        authoritative_completeness_known=specification.authoritative_completeness_known,
        source_reference=specification.source.source_reference,
        standards_release=specification.standards_release,
        limitations=list(specification.limitations) if preview else MT_LIMITATIONS,
        capability=capability,
        capability_summary=capability_summary(capability),
        lane=Lane(specification.lane),
        release=specification.release,
        capability_statement=specification.capability_statement,
        structure_source=specification.structure_source,
    )


def _area_for(specification: MessageSpecification) -> BusinessArea:
    if specification.business_area:
        try:
            return BusinessArea(specification.business_area)
        except ValueError:
            return BusinessArea.OTHER
    return MODULE_TO_AREA.get(specification.workflow_module, BusinessArea.OTHER)


def _mx_spec_from(spec: MxMessageSpec, registry: MxRegistry) -> MessageSpec:
    root = f"/{spec.document_element}/{spec.message_root}"
    groups: list[SpecGroup] = []
    fields: list[SpecField] = []
    seen_groups: set[str] = set()
    preview = spec.lane == Lane.KNOWLEDGE_PREVIEW.value

    for flat in registry.flat(spec.version):
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
                    min_occurs=(
                        1
                        if top_element is None
                        or top_element.presence is Presence.MANDATORY
                        else 0
                    ),
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
                or _inherited_condition(flat.path, spec, registry),
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
    if preview:
        capability = derive_dimensions(
            generated_from_schema=True,
            has_business_rules=bool(spec.require_one_of),
            profile_configured=False,
            reviewed_business_rules=False,
            market_practice_configured=False,
            client_rules_configured=False,
        )
    else:
        capability = capability_dimensions(MessageFormat.MX, spec.message_type)
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
        capability=capability,
        capability_summary=capability_summary(capability),
        lane=Lane(spec.lane),
        release=spec.version,
        capability_statement=spec.capability_statement,
        structure_source="OPERATOR_SUPPLIED_XSD" if preview else None,
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


def _inherited_condition(path: str, spec, registry) -> str | None:  # type: ignore[no-untyped-def]
    """Surface the nearest ancestor's condition so a leaf explains when it applies."""
    by_path = registry.by_path(spec.version)
    parts = path.split("/")
    for depth in range(len(parts) - 1, 2, -1):
        ancestor = by_path.get("/".join(parts[:depth]))
        if ancestor and ancestor.element.condition_explanation:
            return str(ancestor.element.condition_explanation)
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


#: The generate request accepts at most this many inputs; a FULL sample past it is not offered.
MAX_SAMPLE_FIELDS = 500

READINESS_LABELS: dict[Readiness, str] = {
    Readiness.KNOWLEDGE_ONLY: "Knowledge only — structure missing",
    Readiness.STRUCTURE_AVAILABLE: "Structure evidence available; generation not established",
    Readiness.STRUCTURE_VERIFIED: "Structure loads and composes; round trip not established",
    Readiness.GENERATION_READY: "Structure-backed test generation; semantic rules not established",
}


def _entry(
    spec: MessageSpec,
    variants: tuple[SampleVariant, ...],
    *,
    readiness: Readiness = Readiness.GENERATION_READY,
    blockers: list[str] | None = None,
    knowledge_sources: int = 0,
    rules_status: str = "CONFIGURED",
    ai_sample_ready: bool = False,
) -> CatalogueEntry:
    preview = spec.lane is Lane.KNOWLEDGE_PREVIEW
    generatable = readiness is Readiness.GENERATION_READY
    if preview:
        label = READINESS_LABELS[readiness]
        if spec.structure_source == "OPERATOR_SUPPLIED_XSD" and generatable:
            label = "XSD-backed structure; business rules not established"
        if spec.release and spec.release.startswith("SR20"):
            from app.knowledge_base.models import release_lane

            if release_lane(spec.release).value == "FUTURE_TEST":
                label += " · future release, test preview"
    else:
        label = "Configured & validated"
    return CatalogueEntry(
        format=spec.format,
        message_type=spec.message_type,
        version=spec.version,
        name=spec.name,
        short_description=spec.short_description or spec.scope,
        business_area=spec.business_area,
        business_area_label=BUSINESS_AREA_LABELS[spec.business_area],
        generatable=generatable,
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
        lane=spec.lane,
        release=spec.release,
        release_lane=_release_lane_label(spec),
        readiness=readiness,
        readiness_label=label,
        blockers=list(blockers or []),
        structure_source=spec.structure_source,
        rules_status=rules_status,
        knowledge_sources=knowledge_sources,
        ai_sample_ready=ai_sample_ready,
        automation_ready=generatable,
    )


def _release_lane_label(spec: MessageSpec) -> str | None:
    if spec.format is MessageFormat.MT and spec.release:
        from app.knowledge_base.models import release_lane

        return str(release_lane(spec.release).value)
    return None


def _knowledge_only_entry(
    format_: MessageFormat,
    message_type: str,
    release: str | None,
    name: str,
    readiness: Readiness,
    blockers: list[str],
    sources: int,
    structure_source: str | None,
    business_area: str | None,
) -> CatalogueEntry:
    """A message the knowledge base knows but cannot generate. Shown, never faked."""
    try:
        area = BusinessArea(business_area) if business_area else BusinessArea.OTHER
    except ValueError:
        area = BusinessArea.OTHER
    label = READINESS_LABELS[readiness]
    if readiness is Readiness.KNOWLEDGE_ONLY and sources:
        label = "Knowledge available; structure not yet compilable"
    return CatalogueEntry(
        format=format_,
        message_type=message_type,
        version=release if format_ is MessageFormat.MX else None,
        name=name,
        short_description=f"{name} — {label}.",
        business_area=area,
        business_area_label=BUSINESS_AREA_LABELS[area],
        generatable=False,
        output_modes=[],
        field_count=0,
        mandatory_field_count=0,
        sample_variants=[],
        authoritative_completeness_known=False,
        source_reference=structure_source or "KNOWLEDGE_BASE",
        limitations=["Generation is disabled: " + ", ".join(blockers or [readiness.value])],
        capability=CapabilityDimensions(
            structure=StructureStatus.UNVERIFIED,
            business_rules=BusinessRuleStatus.NOT_CONFIGURED,
            market_practice=OverlayStatus.NOT_CONFIGURED,
            client_profile=OverlayStatus.NOT_CONFIGURED,
            external_validation=ExternalValidationStatus.NOT_RUN,
        ),
        capability_summary=label,
        lane=Lane.KNOWLEDGE_PREVIEW,
        release=release,
        release_lane=None,
        readiness=readiness,
        readiness_label=label,
        blockers=list(blockers),
        structure_source=structure_source,
        rules_status="NOT_ESTABLISHED",
        knowledge_sources=sources,
        ai_sample_ready=False,
        automation_ready=False,
    )


def build_catalogue(*, include_preview: bool = True) -> StudioCatalogue:
    """Configured messages first; then, when the knowledge base is enabled, every message
    it discovered — generation-ready preview packs and knowledge-only entries alike, each
    saying exactly what it is."""
    from app.studio.samples import available_variants

    entries: list[CatalogueEntry] = []
    for mt_spec in specification_registry.list():
        spec = message_spec(MessageFormat.MT, mt_spec.message_type)
        entries.append(
            _entry(spec, available_variants(MessageFormat.MT, mt_spec.message_type))
        )
    for mx_spec in mx_registry.all_specs():
        spec = message_spec(MessageFormat.MX, mx_spec.version)
        entries.append(_entry(spec, available_variants(MessageFormat.MX, mx_spec.version)))
    if include_preview:
        entries.extend(_preview_entries())

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
                configured_message_count=sum(
                    1 for entry in subset if entry.lane is Lane.CONFIGURED
                ),
            )
        )
    return StudioCatalogue(
        formats=formats,
        messages=entries,
        profiles=[profile.profile_id for profile in profiles.list()],
        default_profile_id="BASE_DEMO_V1",
    )


def _preview_entries() -> list[CatalogueEntry]:
    from app.config import get_settings

    if not get_settings().knowledge_enabled:
        return []
    from app.knowledge_base.preview import preview_registries
    from app.knowledge_base.service import knowledge_service

    registries = preview_registries()
    source_counts = knowledge_service.source_counts()
    entries: list[CatalogueEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for (format_name, message_type, release), status in sorted(registries.structures.items()):
        seen.add((format_name, message_type, release))
        format_ = MessageFormat(format_name)
        if _shadowed_by_configured(format_, message_type, release):
            continue
        sources = source_counts.get((format_name, message_type, release), 0)
        if status.generation_ready:
            try:
                spec = message_spec(format_, message_type, Lane.KNOWLEDGE_PREVIEW, release)
            except (KeyError, LookupError):
                spec = None
            if spec is not None:
                # Variants are declared from the structure rather than built: building
                # three samples for each of several hundred preview messages on every
                # catalogue call would make the catalogue minutes slow. They are built on
                # first request instead.
                mandatory = sum(1 for f in spec.fields if f.presence is Presence.MANDATORY)
                variants = (SampleVariant.MINIMAL,) + (
                    (SampleVariant.FULL,)
                    if mandatory < len(spec.fields) <= MAX_SAMPLE_FIELDS
                    else ()
                )
                entries.append(
                    _entry(
                        spec,
                        variants,
                        readiness=Readiness(status.readiness.value),
                        blockers=list(status.blockers),
                        knowledge_sources=sources,
                        rules_status="NOT_ESTABLISHED",
                        ai_sample_ready=knowledge_service.sample_cached(
                            format_name, message_type, release
                        ),
                    )
                )
                continue
        entries.append(
            _knowledge_only_entry(
                format_,
                message_type,
                release,
                status.name,
                Readiness(status.readiness.value),
                list(status.blockers),
                sources,
                status.structure_source,
                status.business_area,
            )
        )
    for (format_name, message_type, release), count in sorted(source_counts.items()):
        if (format_name, message_type, release) in seen or format_name not in {"MT", "MX"}:
            continue
        if _shadowed_by_configured(MessageFormat(format_name), message_type, release):
            continue
        entries.append(
            _knowledge_only_entry(
                MessageFormat(format_name),
                message_type,
                release,
                message_type,
                Readiness.KNOWLEDGE_ONLY,
                ["STRUCTURE_SOURCE_MISSING"],
                count,
                None,
                None,
            )
        )
    return entries


def _shadowed_by_configured(format_: MessageFormat, message_type: str, release: str) -> bool:
    """A preview entry for the release the configured lane already serves is not listed:
    the configured pack is the authority for that message in the current live release.
    A future-release preview of the same message (MT541 SR2026 beside configured MT541)
    is a different thing and stays listed."""
    if format_ is MessageFormat.MT:
        if not specification_registry.known(message_type):
            return False
        from app.knowledge_base.models import ReleaseLane, release_lane

        return release_lane(release) is ReleaseLane.CURRENT_LIVE
    return mx_registry.known(release)


def resolve_format(message_type: str) -> MessageFormat:
    """Infer the format from a message type, so callers may omit it."""
    candidate = message_type.strip().upper()
    if candidate.startswith("MT"):
        return MessageFormat.MT
    if mx_registry.known(message_type):
        return MessageFormat.MX
    raise KeyError(f"Unknown message type: {message_type}")


def known_message_type(
    format_: MessageFormat, message_type: str, lane: Lane = Lane.CONFIGURED
) -> bool:
    if lane is Lane.KNOWLEDGE_PREVIEW:
        from app.knowledge_base.preview import preview_registries

        registries = preview_registries()
        if format_ is MessageFormat.MT:
            return registries.known_mt(message_type)
        return registries.known_mx(message_type)
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
