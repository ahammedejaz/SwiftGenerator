"""The one place where a request becomes a message.

Every entry point — the browser wizard, the JSON API and the Excel API — arrives here, so
the three can never disagree about validation, output or classification.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.config import get_settings
from app.profiles.loader import ClientProfile, profiles
from app.rule_engine.binding import value_bag
from app.rule_engine.evaluator import evaluate_rules
from app.rule_engine.registry import rule_pack_registry
from app.specifications.models import MessageSpecification
from app.studio.catalogue import known_message_type, message_spec
from app.studio.models import (
    MT_OUTPUT_MODES,
    MX_OUTPUT_MODES,
    GenerateRequest,
    GenerateResult,
    IssueSeverity,
    Lane,
    LaneProvenance,
    LayerResult,
    LayerState,
    MessageFormat,
    MessageOutputs,
    MessageSpec,
    OutputMode,
    ValidationIssue,
    ValidationLayer,
    ValidationResult,
)
from app.studio.mt.fin import envelope_availability
from app.studio.mt.generator import mt_generator
from app.studio.mx.generator import MxGenerator, check_well_formed, mx_generator
from app.studio.mx.registry import MxRegistry
from app.studio.mx.xsd import SchemaSource, validate_document
from app.studio.store import studio_message_store

DISCLAIMER = (
    "Messages are generated against the selected configured profile and configured message "
    "subset. They are not transmitted through, validated by, or certified by the Swift "
    "network. Interface-generated and network-generated values are never fabricated."
)


class UnknownMessageType(Exception):
    pass


class StudioService:
    def generate(self, request: GenerateRequest, *, source: str = "API") -> GenerateResult:
        if request.lane is Lane.KNOWLEDGE_PREVIEW:
            return self._generate_preview(request, source=source)
        if not known_message_type(request.format, request.message_type):
            raise UnknownMessageType(
                f"{request.message_type} is not a supported {request.format.value} message."
            )
        profile = profiles.get(request.profile_id)
        if request.format is MessageFormat.MT:
            result = self._generate_mt(request, profile)
        else:
            result = self._generate_mx(request, profile)
        if request.persist:
            result.message_id = studio_message_store.save(
                result,
                inputs=request.model_dump(mode="json", by_alias=True),
                source=source,
            )
        return result

    # -- the knowledge-preview lane --------------------------------------------------------

    def _generate_preview(self, request: GenerateRequest, *, source: str) -> GenerateResult:
        """Same validator, same composer, a different registry — named by the caller.

        The preview lane never applies reviewed Rule Packs: none exists for a preview pack,
        and applying a configured message's pack to a differently-sourced structure would
        attribute one release's rules to another. The provenance on the result says so.
        """
        from app.knowledge_base.preview import PreviewUnavailable, preview_registries

        if not get_settings().knowledge_enabled:
            raise UnknownMessageType(
                "The knowledge-preview lane is disabled (KNOWLEDGE_MODE=disabled)."
            )
        registries = preview_registries()
        profile = profiles.get(request.profile_id)
        try:
            if request.format is MessageFormat.MT:
                specification = registries.resolve_mt(request.message_type, request.release)
                result = self._generate_mt(request, profile, specification=specification)
            else:
                mx_spec = registries.resolve_mx(request.release or request.message_type)
                assert registries.mx_registry is not None
                result = self._generate_mx(
                    request,
                    profile,
                    registry=registries.mx_registry,
                    official_xsd=registries.mx_xsd_path(mx_spec),
                    version=mx_spec.version,
                )
        except PreviewUnavailable as error:
            raise UnknownMessageType(f"{error.code}: {error}") from error
        if request.persist:
            result.message_id = studio_message_store.save(
                result,
                inputs=request.model_dump(mode="json", by_alias=True),
                source=source,
            )
        return result

    # -- MT ----------------------------------------------------------------------------

    def _generate_mt(
        self,
        request: GenerateRequest,
        profile: ClientProfile,
        *,
        specification: MessageSpecification | None = None,
    ) -> GenerateResult:
        preview = specification is not None
        spec = (
            message_spec(
                MessageFormat.MT,
                request.message_type,
                Lane.KNOWLEDGE_PREVIEW,
                specification.release if specification else None,
            )
            if preview
            else message_spec(MessageFormat.MT, request.message_type)
        )
        wants = self._requested_modes(request, MT_OUTPUT_MODES)
        build = mt_generator.build(
            request.message_type,
            profile,
            request.fields,
            envelope=request.envelope,
            want_fin=OutputMode.FIN in wants or OutputMode.TXT in wants,
            specification=specification,
        )
        if not preview:
            _apply_rule_packs(
                MessageFormat.MT,
                request.message_type,
                profile,
                [(item.row.row_id, item.value) for item in build.resolved],
                build.errors,
                build.warnings,
            )
        layers = [
            _layer(ValidationLayer.CANONICAL, build.errors),
            _layer(ValidationLayer.STRUCTURE, build.errors),
            _layer(ValidationLayer.FORMAT, build.errors),
            _layer(ValidationLayer.BUSINESS_RULES, build.errors),
            _layer(ValidationLayer.MARKET_PRACTICE, build.errors),
            _layer(ValidationLayer.CLIENT_PROFILE, build.errors),
        ]
        if build.fin is not None:
            layers.append(
                LayerResult(
                    layer=ValidationLayer.FIN_ENVELOPE,
                    state=LayerState.PASSED,
                    detail="Blocks 1, 2 and 4 were built from configured interface values.",
                )
            )
        else:
            blocked = build.fin_blocked_reason or "FIN output was not requested."
            layers.append(
                LayerResult(
                    layer=ValidationLayer.FIN_ENVELOPE,
                    state=LayerState.SKIPPED if OutputMode.FIN in wants else
                    LayerState.NOT_APPLICABLE,
                    detail=blocked,
                )
            )
        layers.extend(
            LayerResult(layer=layer, state=LayerState.NOT_APPLICABLE, detail="MX-only layer.")
            for layer in (
                ValidationLayer.XML_WELL_FORMED,
                ValidationLayer.XSD,
                ValidationLayer.APPHDR_CONSISTENCY,
            )
        )
        valid = not build.errors
        outputs = MessageOutputs()
        if OutputMode.BLOCK4 in wants:
            outputs.block4 = build.block_4
        if OutputMode.FIN in wants:
            outputs.fin = build.fin
        if OutputMode.TXT in wants:
            outputs.txt = build.fin or build.block_4
        if OutputMode.CANONICAL_JSON in wants:
            outputs.canonical_json = {
                "format": "MT",
                "messageType": spec.message_type,
                "profileId": profile.profile_id,
                "profileVersion": profile.version,
                "scenarioId": request.scenario_id,
                "fields": [
                    {
                        "id": item.row.row_id,
                        "sequence": item.row.sequence_path,
                        "sequenceCode": item.row.sequence_code,
                        "occurrence": item.occurrence,
                        "tag": item.row.tag,
                        "qualifier": item.row.qualifier,
                        "option": item.row.option,
                        "displayName": item.row.business_name,
                        "businessPath": item.row.business_path,
                        "presence": item.row.presence.value,
                        "value": item.value,
                        "origin": item.origin.value,
                    }
                    for item in build.resolved
                ],
            }
        return GenerateResult(
            correlation_id=str(uuid4()),
            scenario_id=request.scenario_id,
            format=MessageFormat.MT,
            message_type=spec.message_type,
            version=None,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            valid=valid,
            validation=_result(valid, layers, build.errors, build.warnings),
            outputs=outputs,
            envelope_fields=build.envelope_fields,
            rendered_lines=build.rendered_lines,
            checksum=build.checksum,
            available_output_modes=[
                mode
                for mode in MT_OUTPUT_MODES
                if mode is not OutputMode.FIN or build.fin is not None
            ],
            disclaimer=DISCLAIMER,
            lane=spec.lane,
            provenance=_provenance(spec, rules_applied=not preview),
        )

    # -- MX ----------------------------------------------------------------------------

    def _generate_mx(
        self,
        request: GenerateRequest,
        profile: ClientProfile,
        *,
        registry: MxRegistry | None = None,
        official_xsd: Path | None = None,
        version: str | None = None,
    ) -> GenerateResult:
        preview = registry is not None
        generator = MxGenerator(registry) if registry is not None else mx_generator
        identifier = version or request.message_type
        spec = (
            message_spec(MessageFormat.MX, identifier, Lane.KNOWLEDGE_PREVIEW, version)
            if preview
            else message_spec(MessageFormat.MX, request.message_type)
        )
        raw_spec = generator.specification(identifier)
        wants = self._requested_modes(request, MX_OUTPUT_MODES)
        build = generator.build(
            identifier,
            profile,
            request.elements,
            envelope=request.envelope,
            include_app_hdr=OutputMode.APPHDR in wants or OutputMode.XML in wants,
        )
        errors = list(build.errors)
        warnings = list(build.warnings)
        if not preview:
            _apply_rule_packs(
                MessageFormat.MX,
                request.message_type,
                profile,
                [(item.flat.path, item.value) for item in build.resolved],
                errors,
                warnings,
            )

        well_formed_issue = check_well_formed(build.xml)
        if well_formed_issue is not None:
            errors.append(well_formed_issue)

        xsd_outcome = validate_document(raw_spec, build.document, official_path=official_xsd)
        errors.extend(xsd_outcome.issues)

        layers = [
            _layer(ValidationLayer.CANONICAL, errors),
            _layer(ValidationLayer.STRUCTURE, errors),
            _layer(ValidationLayer.FORMAT, errors),
            _layer(ValidationLayer.BUSINESS_RULES, errors),
            _layer(ValidationLayer.MARKET_PRACTICE, errors),
            _layer(ValidationLayer.CLIENT_PROFILE, errors),
            LayerResult(
                layer=ValidationLayer.FIN_ENVELOPE,
                state=LayerState.NOT_APPLICABLE,
                detail="MX messages do not use FIN blocks.",
            ),
            LayerResult(
                layer=ValidationLayer.XML_WELL_FORMED,
                state=LayerState.FAILED if well_formed_issue else LayerState.PASSED,
                detail="The generated XML parses cleanly."
                if not well_formed_issue
                else well_formed_issue.message,
            ),
            LayerResult(
                layer=ValidationLayer.XSD,
                state=(
                    LayerState.SKIPPED
                    if not xsd_outcome.performed
                    else LayerState.PASSED
                    if xsd_outcome.passed
                    else LayerState.FAILED
                ),
                detail=xsd_outcome.detail,
            ),
            LayerResult(
                layer=ValidationLayer.APPHDR_CONSISTENCY,
                state=LayerState.PASSED if build.app_hdr else LayerState.SKIPPED,
                detail=(
                    "The header message definition identifier matches the document namespace."
                    if build.app_hdr
                    else "No Business Application Header was produced."
                ),
            ),
        ]
        valid = not errors
        outputs = MessageOutputs()
        if OutputMode.DOCUMENT in wants:
            outputs.document = build.document
        if OutputMode.APPHDR in wants:
            outputs.app_hdr = build.app_hdr
        if OutputMode.XML in wants:
            outputs.xml = build.xml
        if OutputMode.CANONICAL_JSON in wants:
            outputs.canonical_json = {
                "format": "MX",
                "messageType": spec.message_type,
                "version": spec.version,
                "namespace": spec.namespace,
                "profileId": profile.profile_id,
                "profileVersion": profile.version,
                "scenarioId": request.scenario_id,
                "schemaSource": xsd_outcome.schema_source.value,
                "elements": [
                    {
                        "path": item.flat.path,
                        "occurrence": item.occurrence,
                        "displayName": item.flat.element.display_name,
                        "dataType": item.flat.element.data_type.value
                        if item.flat.element.data_type
                        else None,
                        "businessPath": item.flat.element.business_path,
                        "value": item.value,
                        "currency": item.currency,
                    }
                    for item in build.resolved
                ],
            }
        available = list(MX_OUTPUT_MODES)
        if build.app_hdr is None:
            available = [mode for mode in available if mode is not OutputMode.APPHDR]
        return GenerateResult(
            correlation_id=str(uuid4()),
            scenario_id=request.scenario_id,
            format=MessageFormat.MX,
            message_type=spec.message_type,
            version=spec.version,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            valid=valid,
            validation=_result(valid, layers, errors, warnings),
            outputs=outputs,
            envelope_fields=build.envelope_fields,
            rendered_lines=build.rendered_lines,
            checksum=build.checksum,
            available_output_modes=available,
            disclaimer=DISCLAIMER,
            lane=spec.lane,
            provenance=_provenance(
                spec,
                rules_applied=not preview,
                validation_level=f"XSD:{xsd_outcome.schema_source.value}",
            ),
        )

    # -- helpers -----------------------------------------------------------------------

    @staticmethod
    def _requested_modes(
        request: GenerateRequest, defaults: list[OutputMode]
    ) -> set[OutputMode]:
        if not request.output_modes:
            return set(defaults)
        return {mode for mode in request.output_modes if mode in defaults} or set(defaults)

    @staticmethod
    def fin_availability(profile_id: str) -> list[ValidationIssue]:
        return envelope_availability(profiles.get(profile_id))

    @staticmethod
    def schema_source(message_type: str) -> SchemaSource:
        spec = mx_generator.specification(message_type)
        outcome = validate_document(spec, mx_generator.compose_document(spec, []))
        return outcome.schema_source


def _provenance(
    spec: MessageSpec, *, rules_applied: bool, validation_level: str | None = None
) -> LaneProvenance:
    preview = spec.lane is Lane.KNOWLEDGE_PREVIEW
    release_lane_value: str | None = None
    if spec.format is MessageFormat.MT and spec.release:
        from app.knowledge_base.models import release_lane

        release_lane_value = release_lane(spec.release).value
    return LaneProvenance(
        lane=spec.lane,
        release=spec.release,
        release_lane=release_lane_value,
        structure_source=spec.structure_source or "CONFIGURED_REPOSITORY_SUBSET",
        rule_status=(
            "REVIEWED_RULE_PACKS_APPLIED" if rules_applied else "NOT_ESTABLISHED"
        ),
        validation_level=validation_level
        or ("STRUCTURE_FORMAT_ONLY" if preview else "STRUCTURE_FORMAT_BUSINESS_PROFILE"),
        capability_statement=spec.capability_statement
        or (
            "Configured repository subset; not reconciled against a licensed specification."
        ),
        source_provenance=[spec.source_reference],
    )


def _apply_rule_packs(
    format_: MessageFormat,
    message_type: str,
    profile: ClientProfile,
    entries: list[tuple[str, str]],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> None:
    """Evaluate the installed reviewed rule packs and file their findings.

    One call site for both formats and all three entry points, so the browser, the JSON
    API and the Excel path cannot execute different rules. Nothing here calls a model:
    evaluation is a pure walk over the values the composer already resolved.
    """
    effective = rule_pack_registry.effective(format_, message_type, profile.profile_id)
    if effective.empty:
        return
    for issue in evaluate_rules(effective, value_bag(entries)):
        if issue.severity is IssueSeverity.ERROR:
            errors.append(issue)
        else:
            warnings.append(issue)


def _layer(layer: ValidationLayer, issues: list[ValidationIssue]) -> LayerResult:
    failed = [issue for issue in issues if issue.layer is layer]
    if failed:
        return LayerResult(
            layer=layer,
            state=LayerState.FAILED,
            detail=f"{len(failed)} issue(s) found.",
        )
    return LayerResult(layer=layer, state=LayerState.PASSED, detail="No issues found.")


def _result(
    valid: bool,
    layers: list[LayerResult],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> ValidationResult:
    real_errors = [issue for issue in errors if issue.severity is IssueSeverity.ERROR]
    all_warnings = [
        *[issue for issue in errors if issue.severity is IssueSeverity.WARNING],
        *warnings,
    ]
    count = len(real_errors)
    if count == 0:
        summary = "Ready to generate"
    elif count == 1:
        summary = "1 issue needs attention"
    else:
        summary = f"{count} issues need attention"
    return ValidationResult(
        valid=valid and count == 0,
        summary=summary,
        layers=layers,
        errors=real_errors,
        warnings=all_warnings,
    )


studio_service = StudioService()
