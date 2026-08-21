"""The `/api/v1` automation API.

This is the whole contract. The browser UI calls exactly these endpoints, so there is no
capability a manual tester has that an automation tester cannot reach, and no way for the
two to drift apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from io import BytesIO
from typing import Annotated
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError

from app.config import get_settings
from app.studio import intelligence
from app.studio.catalogue import build_catalogue, known_message_type, message_spec, resolve_format
from app.studio.coverage import UnifiedCoverage, build_coverage
from app.studio.diff import build_diff
from app.studio.excel import (
    ExcelFormatError,
    ParsedScenario,
    build_template,
    parse_workbook,
    validate_upload,
)
from app.studio.models import (
    DiffRequest,
    DiffResult,
    ElementInput,
    EnvelopeOverride,
    ExcelGenerateResponse,
    ExcelScenarioResult,
    FieldInput,
    GenerateRequest,
    GenerateResult,
    ImportRequest,
    ImportResult,
    IntelligenceDetail,
    IntelligenceSearchResponse,
    IssueSeverity,
    Lane,
    LayerResult,
    LayerState,
    MessageFormat,
    MessageSpec,
    OutputMode,
    RecentMessage,
    SampleMessage,
    SampleVariant,
    StudioCatalogue,
    ValidateRequest,
    ValidationIssue,
    ValidationLayer,
    ValidationResult,
)
from app.studio.mt.parser import MtImportError
from app.studio.mt.parser import parse_message as parse_mt
from app.studio.mx.parser import MxImportError
from app.studio.mx.parser import parse_message as parse_mx
from app.studio.samples import available_variants, build_sample
from app.studio.security import AutomationCaller
from app.studio.service import DISCLAIMER, UnknownMessageType, studio_service
from app.studio.sources import SourceReadinessReport, build_readiness
from app.studio.store import studio_message_store

router = APIRouter(prefix="/api/v1", tags=["Financial Message Studio"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ACCEPTED_UPLOAD_TYPES = {XLSX_MEDIA_TYPE, "application/octet-stream", "application/zip"}

#: Filename extension and media type for each output mode.
OUTPUT_FILE_TYPES: dict[OutputMode, tuple[str, str]] = {
    OutputMode.BLOCK4: ("block4.txt", "text/plain; charset=utf-8"),
    OutputMode.FIN: ("fin", "text/plain; charset=utf-8"),
    OutputMode.TXT: ("txt", "text/plain; charset=utf-8"),
    OutputMode.XML: ("xml", "application/xml; charset=utf-8"),
    OutputMode.APPHDR: ("apphdr.xml", "application/xml; charset=utf-8"),
    OutputMode.DOCUMENT: ("document.xml", "application/xml; charset=utf-8"),
    OutputMode.CANONICAL_JSON: ("canonical.json", "application/json"),
}


def _resolve(format_: MessageFormat | None, message_type: str) -> MessageFormat:
    if format_ is not None:
        return format_
    try:
        return resolve_format(message_type)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown message type: {message_type}"
        ) from error


def _require_known(format_: MessageFormat, message_type: str, lane: Lane = Lane.CONFIGURED) -> None:
    if lane is Lane.KNOWLEDGE_PREVIEW and not get_settings().knowledge_enabled:
        raise HTTPException(
            status_code=404,
            detail="The knowledge-preview lane is disabled (KNOWLEDGE_MODE=disabled).",
        )
    if not known_message_type(format_, message_type, lane):
        detail = f"{message_type} is not a supported {format_.value} message."
        if lane is Lane.KNOWLEDGE_PREVIEW:
            detail = (
                f"STRUCTURE_SOURCE_MISSING: {message_type} has no generation-ready local "
                "Structure Pack in the knowledge-preview lane."
            )
        raise HTTPException(status_code=404, detail=detail)


def _spec_or_404(
    format_: MessageFormat, message_type: str, lane: Lane, release: str | None
) -> MessageSpec:
    try:
        return message_spec(format_, message_type, lane, release)
    except LookupError as error:
        code = getattr(error, "code", "MESSAGE_GENERATION_NOT_READY")
        raise HTTPException(status_code=404, detail=f"{code}: {error}") from error


# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------


@router.get("/catalogue", response_model=StudioCatalogue)
def get_catalogue(caller: AutomationCaller) -> StudioCatalogue:
    """Every format, business area and message the platform can generate."""
    del caller
    return build_catalogue()


@router.get("/coverage", response_model=UnifiedCoverage)
def get_coverage(caller: AutomationCaller) -> UnifiedCoverage:
    """What this repository implements for every configured message, in both formats.

    Every figure is out of the configured subset, never out of the standard, and each
    carries the basis it was measured on. This is the same data `make coverage` renders
    into `docs/generated/message-coverage.md`, so the document and the API cannot drift.
    """
    return build_coverage()


@router.get("/sources", response_model=SourceReadinessReport)
def get_source_readiness(caller: AutomationCaller) -> SourceReadinessReport:
    """Where an authorised specification artifact goes, and what changes when it arrives.

    Nothing licensed is reproduced here. This reports the receiving end: the drop location,
    the setting that redirects it, what is being read today, and what a real artifact would
    unlock.
    """
    return build_readiness()


@router.get("/messages/{message_type}/spec", response_model=MessageSpec)
def get_message_spec(
    message_type: str,
    caller: AutomationCaller,
    format: Annotated[MessageFormat | None, Query()] = None,
    lane: Annotated[Lane, Query()] = Lane.CONFIGURED,
    release: Annotated[str | None, Query(max_length=32)] = None,
) -> MessageSpec:
    """Every input slot for a message, with presence, format, examples and guidance.

    ``lane=KNOWLEDGE_PREVIEW`` reads a local Structure Pack compiled by the knowledge sync;
    ``release`` picks one where several exist.
    """
    del caller
    resolved = _resolve_lane(format, message_type, lane)
    _require_known(resolved, message_type, lane)
    return _spec_or_404(resolved, message_type, lane, release)


@router.get("/messages/{message_type}/samples", response_model=list[SampleMessage])
def list_samples(
    message_type: str,
    caller: AutomationCaller,
    format: Annotated[MessageFormat | None, Query()] = None,
    lane: Annotated[Lane, Query()] = Lane.CONFIGURED,
    release: Annotated[str | None, Query(max_length=32)] = None,
) -> list[SampleMessage]:
    del caller
    resolved = _resolve_lane(format, message_type, lane)
    _require_known(resolved, message_type, lane)
    _spec_or_404(resolved, message_type, lane, release)
    return [
        build_sample(resolved, message_type, variant, lane, release)
        for variant in available_variants(resolved, message_type, lane, release)
    ]


@router.get("/messages/{message_type}/samples/{variant}", response_model=SampleMessage)
def get_sample(
    message_type: str,
    variant: SampleVariant,
    caller: AutomationCaller,
    format: Annotated[MessageFormat | None, Query()] = None,
    lane: Annotated[Lane, Query()] = Lane.CONFIGURED,
    release: Annotated[str | None, Query(max_length=32)] = None,
) -> SampleMessage:
    del caller
    resolved = _resolve_lane(format, message_type, lane)
    _require_known(resolved, message_type, lane)
    _spec_or_404(resolved, message_type, lane, release)
    if variant not in available_variants(resolved, message_type, lane, release):
        raise HTTPException(
            status_code=404,
            detail=f"{message_type} has no {variant.value} sample.",
        )
    return build_sample(resolved, message_type, variant, lane, release)


def _resolve_lane(format_: MessageFormat | None, message_type: str, lane: Lane) -> MessageFormat:
    if format_ is not None:
        return format_
    candidate = message_type.strip().upper()
    if candidate.startswith("MT"):
        return MessageFormat.MT
    if lane is Lane.KNOWLEDGE_PREVIEW:
        return MessageFormat.MX
    return _resolve(format_, message_type)


# --------------------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------------------


@router.post("/messages/validate", response_model=GenerateResult)
def validate_message(request: ValidateRequest, caller: AutomationCaller) -> GenerateResult:
    """Validate without persisting. Returns the same shape as generate."""
    del caller
    return _generate(GenerateRequest(**request.model_dump()), persist=False, source="API")


@router.post("/messages/generate", response_model=GenerateResult)
def generate_message(request: GenerateRequest, caller: AutomationCaller) -> GenerateResult:
    """Turn tag-level (MT) or element-level (MX) data into a complete message."""
    return _generate(request, persist=request.persist, source=_source(caller))


def _source(caller: AutomationCaller) -> str:
    return "API" if caller.authenticated else "API_OPEN"


def _generate(request: GenerateRequest, *, persist: bool, source: str) -> GenerateResult:
    payload = request.model_copy(update={"persist": persist})
    try:
        return studio_service.generate(payload, source=source)
    except UnknownMessageType as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error


def _import_format(text: str) -> MessageFormat:
    """Decide which parser a pasted message belongs to, from the message itself.

    An ISO 20022 document opens with markup; a FIN message opens with a block, and a
    pasted text block is a run of colon-prefixed lines. Anything else is refused by name
    rather than guessed at, because handing prose to a parser produces a confident,
    misleading error about the wrong format.
    """
    stripped = text.lstrip()
    if stripped.startswith("<") or "<Document" in text or "urn:iso:std:iso:20022" in text:
        return MessageFormat.MX
    if stripped.startswith("{") or ":16R:" in text or stripped.startswith(":"):
        return MessageFormat.MT
    raise HTTPException(
        status_code=422,
        detail="That does not look like a SWIFT message. Paste an ISO 20022 document, "
        "a FIN message, or an MT text block.",
    )


@dataclass
class _Existing:
    """What reading an existing message produced, whichever format it turned out to be."""

    format: MessageFormat
    message_type: str
    version: str | None = None
    namespace: str | None = None
    app_hdr_present: bool = False
    fin_blocks: list[str] = dataclass_field(default_factory=list)
    fields: list[FieldInput] = dataclass_field(default_factory=list)
    elements: list[ElementInput] = dataclass_field(default_factory=list)
    envelope: EnvelopeOverride | None = None
    errors: list[ValidationIssue] = dataclass_field(default_factory=list)
    warnings: list[ValidationIssue] = dataclass_field(default_factory=list)


def _read_existing(
    text: str,
    message_type: str | None,
    lane: Lane = Lane.CONFIGURED,
    release: str | None = None,
) -> _Existing:
    """Read a pasted message with whichever parser its own content calls for.

    Shared by import and by diff so the two can never disagree about what a message says —
    which matters more here than anywhere, because the diff endpoint's whole job is to
    compare what was read with what was written.
    """
    format_ = _import_format(text)
    preview_registry = None
    preview_spec = None
    if lane is Lane.KNOWLEDGE_PREVIEW:
        from app.knowledge_base.preview import PreviewUnavailable, preview_registries

        registries = preview_registries()
        if format_ is MessageFormat.MX:
            preview_registry = registries.mx_registry
            if preview_registry is None:
                raise HTTPException(
                    status_code=404,
                    detail="STRUCTURE_SOURCE_MISSING: no knowledge-preview MX packs are loaded.",
                )
        else:
            if not message_type:
                raise HTTPException(
                    status_code=422,
                    detail="KNOWLEDGE_RELEASE_REQUIRED: name the message type (and release) "
                    "to import against the knowledge-preview lane.",
                )
            try:
                preview_spec = registries.resolve_mt(message_type, release)
            except PreviewUnavailable as error:
                raise HTTPException(status_code=404, detail=f"{error.code}: {error}") from error
    if format_ is MessageFormat.MX:
        try:
            mx = parse_mx(text, preview_registry)
        except MxImportError as error:
            raise HTTPException(status_code=422, detail=error.issue.message) from error
        return _Existing(
            format=MessageFormat.MX,
            message_type=mx.specification.message_type,
            version=mx.specification.version,
            namespace=mx.specification.namespace,
            app_hdr_present=mx.app_hdr_present,
            elements=mx.elements,
            envelope=mx.envelope,
            errors=mx.errors,
            warnings=mx.warnings,
        )
    try:
        mt = parse_mt(text, message_type=message_type, specification=preview_spec)
    except MtImportError as error:
        raise HTTPException(status_code=422, detail=error.issue.message) from error
    return _Existing(
        format=MessageFormat.MT,
        message_type=mt.specification.message_type,
        fin_blocks=mt.blocks,
        fields=mt.fields,
        envelope=mt.envelope,
        errors=mt.errors,
        warnings=mt.warnings,
    )


def _merge_import_issues(
    generated: GenerateResult,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> GenerateResult:
    """Fold what could not be read into the validation the caller already looks at.

    Listing them separately as well is not enough: a caller that checks only `valid` would
    otherwise treat a half-imported message as a faithful one.
    """
    if not errors and not warnings:
        return generated
    validation = generated.validation
    merged = ValidationResult(
        valid=validation.valid and not errors,
        summary=validation.summary,
        layers=validation.layers,
        errors=[*errors, *validation.errors],
        warnings=[*warnings, *validation.warnings],
    )
    merged.summary = _summarise(merged)
    return generated.model_copy(update={"validation": merged, "valid": merged.valid})


@router.post("/messages/diff", response_model=DiffResult)
def diff_message(request: DiffRequest, caller: AutomationCaller) -> DiffResult:
    """Regenerate from these values and compare the result with a message you already have.

    This is the honest end of the round trip. `Compose(Parse(Compose(v))) == Compose(v)` is
    asserted in the test suite, but a tester holding two messages that differ needs to know
    *why* they differ, and the answer is almost never "something is wrong": it is a value
    they edited, a field written back in specification order, or a trailer the studio
    refuses to invent. Every difference is attributed to one of those, and anything that
    fits none of them is reported as unexplained rather than dressed up as normalisation.

    Deterministic throughout. No model is called.
    """
    read = _read_existing(request.original, request.message_type)
    if read.format is not request.format:
        raise HTTPException(
            status_code=422,
            detail=f"The message you supplied is {read.format.value}, but the values are "
            f"{request.format.value}. Compare a message with values of the same format.",
        )

    generated = _generate(
        request.as_generate_request(),
        persist=request.persist,
        source=_source(caller),
    )
    generated = _merge_import_issues(generated, read.errors, read.warnings)

    diff = build_diff(
        format_=read.format,
        original=request.original,
        outputs=generated.outputs,
        imported_fields=read.fields,
        imported_elements=read.elements,
        submitted_fields=request.fields,
        submitted_elements=request.elements,
        issues=[*read.errors, *read.warnings],
        rendered_lines=generated.rendered_lines,
    )
    return DiffResult(
        format=read.format,
        message_type=generated.message_type,
        result=generated,
        diff=diff,
        import_issues=read.errors,
        import_warnings=read.warnings,
        disclaimer=DISCLAIMER,
    )


@router.post("/messages/import", response_model=ImportResult)
def import_message(request: ImportRequest, caller: AutomationCaller) -> ImportResult:
    """Read an existing MT or MX message back into canonical values.

    The parsed values are handed straight to the ordinary generation path, so an imported
    message is regenerated by exactly the code that generates every other message. That is
    what makes the round trip meaningful: if import and generation could disagree, comparing
    them would prove nothing.

    Anything the message contained that could not be imported is reported. It is folded
    into the returned validation as well as listed separately, so a partial import can never
    be mistaken for a faithful one.
    """
    text = request.content
    read = _read_existing(text, request.message_type, request.lane, request.release)

    imported_type = (
        read.message_type
        if read.format is MessageFormat.MT
        else (read.version or read.message_type)
    )
    generate = GenerateRequest(
        format=read.format,
        message_type=imported_type,
        profile_id=request.profile_id,
        scenario_id=request.scenario_id,
        fields=read.fields,
        elements=read.elements,
        envelope=read.envelope,
        output_modes=request.output_modes,
        persist=request.persist,
        lane=request.lane,
        release=request.release if read.format is MessageFormat.MT else read.version,
    )
    generated = _generate(generate, persist=request.persist, source=_source(caller))
    generated = _merge_import_issues(generated, read.errors, read.warnings)

    # Nothing has been edited yet, so the values that went in are the values that came out.
    diff = build_diff(
        format_=read.format,
        original=text,
        outputs=generated.outputs,
        imported_fields=read.fields,
        imported_elements=read.elements,
        submitted_fields=read.fields,
        submitted_elements=read.elements,
        issues=[*read.errors, *read.warnings],
        rendered_lines=generated.rendered_lines,
    )

    return ImportResult(
        format=read.format,
        message_type=read.message_type,
        version=read.version,
        namespace=read.namespace,
        profile_id=request.profile_id,
        app_hdr_present=read.app_hdr_present,
        fin_blocks=read.fin_blocks,
        element_count=len(read.elements) + len(read.fields),
        elements=read.elements,
        fields=read.fields,
        envelope=read.envelope,
        import_issues=read.errors,
        import_warnings=read.warnings,
        result=generated,
        diff=diff,
        disclaimer=DISCLAIMER,
    )


def _summarise(validation: ValidationResult) -> str:
    count = len(validation.errors)
    if count == 0:
        return "Ready to generate"
    return "1 issue needs attention" if count == 1 else f"{count} issues need attention"


@router.post("/messages/generate-from-excel", response_model=ExcelGenerateResponse)
async def generate_from_excel(
    caller: AutomationCaller,
    file: Annotated[UploadFile, File()],
    profile_id: Annotated[str, Query(alias="profileId")] = "BASE_DEMO_V1",
    output_mode: Annotated[list[OutputMode] | None, Query(alias="outputMode")] = None,
    persist: Annotated[bool, Query()] = True,
    lane: Annotated[Lane, Query()] = Lane.CONFIGURED,
    release: Annotated[str | None, Query(max_length=32)] = None,
) -> ExcelGenerateResponse:
    """Upload a tag-level (MT) or element-level (MX) workbook and get generated messages back.

    One ``ScenarioID`` becomes one message. A scenario that fails does not stop the others:
    the response reports every scenario with its own validation. ``lane`` and ``release``
    apply to every scenario in the workbook; the preview lane is never implicit.
    """
    settings = get_settings()
    if file.content_type not in ACCEPTED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Upload an .xlsx workbook. Download a template if you need the layout.",
        )
    content = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    try:
        validate_upload(content, file.filename or "upload.xlsx", settings.max_upload_bytes)
        parsed = parse_workbook(
            content,
            default_profile_id=profile_id,
            max_rows=settings.max_bulk_rows,
        )
    except ExcelFormatError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if len(parsed.scenarios) > settings.max_excel_scenarios:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The workbook has {len(parsed.scenarios)} scenarios; the limit is "
                f"{settings.max_excel_scenarios}. Split it into smaller workbooks."
            ),
        )

    results = [
        _run_scenario(
            scenario,
            parsed.format,
            profile_id,
            output_mode,
            persist,
            _source(caller),
            lane=lane,
            release=release,
        )
        for scenario in parsed.scenarios
    ]
    generated = sum(1 for item in results if item.status == "GENERATED")
    return ExcelGenerateResponse(
        request_id=str(uuid4()),
        format=parsed.format,
        total_scenarios=len(results),
        generated=generated,
        failed=len(results) - generated,
        results=results,
        disclaimer=DISCLAIMER,
    )


def _run_scenario(
    scenario: ParsedScenario,
    format_: MessageFormat,
    default_profile_id: str,
    output_mode: list[OutputMode] | None,
    persist: bool,
    source: str,
    *,
    lane: Lane = Lane.CONFIGURED,
    release: str | None = None,
) -> ExcelScenarioResult:
    if scenario.issues:
        return _failed_scenario(scenario, format_, scenario.issues)
    if not known_message_type(format_, scenario.message_type, lane):
        return _failed_scenario(
            scenario,
            format_,
            [
                ValidationIssue(
                    rule_id="EXCEL_UNSUPPORTED_MESSAGE_TYPE",
                    severity=IssueSeverity.ERROR,
                    layer=ValidationLayer.CANONICAL,
                    message=f"{scenario.message_type} is not a supported {format_.value} message.",
                    suggestion="Call GET /api/v1/catalogue for the supported message types.",
                )
            ],
        )
    try:
        result = studio_service.generate(
            GenerateRequest(
                format=format_,
                message_type=scenario.message_type,
                profile_id=scenario.profile_id or default_profile_id,
                scenario_id=scenario.scenario_id,
                fields=scenario.fields,
                elements=scenario.elements,
                output_modes=output_mode,
                persist=persist,
                lane=lane,
                release=release,
            ),
            source=f"EXCEL_{source}",
        )
    except (UnknownMessageType, KeyError, ValidationError) as error:
        return _failed_scenario(
            scenario,
            format_,
            [
                ValidationIssue(
                    rule_id="EXCEL_SCENARIO_FAILED",
                    severity=IssueSeverity.ERROR,
                    layer=ValidationLayer.CANONICAL,
                    message=str(error).strip("'\""),
                    suggestion="Correct the rows for this scenario and upload again.",
                )
            ],
        )
    return ExcelScenarioResult(
        scenario_id=scenario.scenario_id,
        row_numbers=scenario.row_numbers,
        format=result.format,
        message_type=result.message_type,
        status="GENERATED" if result.valid else "INVALID",
        valid=result.valid,
        validation=result.validation,
        outputs=result.outputs,
        message_id=result.message_id,
        checksum=result.checksum,
        lane=result.lane,
        provenance=result.provenance,
    )


def _failed_scenario(
    scenario: ParsedScenario, format_: MessageFormat, issues: list[ValidationIssue]
) -> ExcelScenarioResult:
    count = len(issues)
    return ExcelScenarioResult(
        scenario_id=scenario.scenario_id,
        row_numbers=scenario.row_numbers,
        format=format_,
        message_type=scenario.message_type or None,
        status="FAILED",
        valid=False,
        validation=ValidationResult(
            valid=False,
            summary="1 issue needs attention" if count == 1 else f"{count} issues need attention",
            layers=[
                LayerResult(
                    layer=ValidationLayer.CANONICAL,
                    state=LayerState.FAILED,
                    detail="The workbook rows could not be turned into a message.",
                )
            ],
            errors=issues,
        ),
    )


# --------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------


@router.get("/templates/{format}.xlsx")
def download_template(
    format: MessageFormat,
    caller: AutomationCaller,
    message_type: Annotated[list[str] | None, Query(alias="messageType")] = None,
    lane: Annotated[Lane, Query()] = Lane.CONFIGURED,
    release: Annotated[str | None, Query(max_length=32)] = None,
) -> Response:
    """A ready-to-edit workbook generated from the message specification.

    With ``lane=KNOWLEDGE_PREVIEW`` the workbook is generated from the named local
    Structure Pack(s) — no hand-written template exists for any message.
    """
    del caller
    if message_type:
        for candidate in message_type:
            _require_known(format, candidate, lane)
    content = build_template(format, message_type, lane=lane, release=release)
    name = f"financial-message-studio-{format.value.lower()}-template.xlsx"
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# --------------------------------------------------------------------------------------
# Message Intelligence
# --------------------------------------------------------------------------------------


@router.get("/intelligence/search", response_model=IntelligenceSearchResponse)
def search_intelligence(
    caller: AutomationCaller,
    q: Annotated[str, Query(min_length=1, max_length=120)],
    format: Annotated[MessageFormat | None, Query()] = None,
    message_type: Annotated[str | None, Query(alias="messageType")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> IntelligenceSearchResponse:
    """Search MT tags and MX elements together. Deterministic; no model call is made."""
    del caller
    return intelligence.search(q, format_=format, message_type=message_type, limit=limit)


@router.get("/intelligence/field", response_model=IntelligenceDetail)
def get_intelligence_detail(
    caller: AutomationCaller,
    id: Annotated[str, Query(min_length=1, max_length=500)],
) -> IntelligenceDetail:
    """Everything known about one field or element, including it shown in a real sample."""
    del caller
    try:
        return intelligence.detail(id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error


# --------------------------------------------------------------------------------------
# Recent messages and downloads
# --------------------------------------------------------------------------------------


@router.get("/messages/recent", response_model=list[RecentMessage])
def list_recent(
    caller: AutomationCaller,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    format: Annotated[MessageFormat | None, Query()] = None,
) -> list[RecentMessage]:
    del caller
    return studio_message_store.recent(limit=limit, format_=format)


@router.get("/messages/id/{message_id}")
def get_message(caller: AutomationCaller, message_id: str) -> dict[str, object]:
    del caller
    try:
        summary, outputs = studio_message_store.get(message_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error
    return {
        "message": summary.model_dump(mode="json", by_alias=True),
        "outputs": outputs.model_dump(mode="json", by_alias=True),
        "inputs": studio_message_store.inputs(message_id),
        "disclaimer": DISCLAIMER,
    }


@router.get("/messages/id/{message_id}/download/{output}")
def download_message(caller: AutomationCaller, message_id: str, output: OutputMode) -> Response:
    """Download one output exactly as generated — no added formatting characters."""
    del caller
    try:
        summary, outputs = studio_message_store.get(message_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error
    payload = _output_text(outputs, output)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"{summary.message_type} was not generated with {output.value} output.",
        )
    extension, media_type = OUTPUT_FILE_TYPES[output]
    stem = f"{summary.message_type.replace('.', '_')}_{message_id[:8]}"
    return Response(
        content=payload.encode(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{stem}.{extension}"'},
    )


@router.get("/messages/id/{message_id}/evidence.zip")
def download_evidence(caller: AutomationCaller, message_id: str) -> Response:
    """Every output plus the validation report, for attaching to a test result."""
    del caller
    try:
        summary, outputs = studio_message_store.get(message_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error).strip("'\"")) from error
    stem = f"{summary.message_type.replace('.', '_')}_{message_id[:8]}"
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for mode in OutputMode:
            payload = _output_text(outputs, mode)
            if payload is None:
                continue
            extension, _ = OUTPUT_FILE_TYPES[mode]
            archive.writestr(f"{stem}.{extension}", payload)
        archive.writestr(
            f"{stem}.metadata.json",
            json.dumps(
                {
                    **summary.model_dump(mode="json", by_alias=True),
                    "inputs": studio_message_store.inputs(message_id),
                    "disclaimer": DISCLAIMER,
                    "generatedAt": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
        )
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{stem}.evidence.zip"'},
    )


def _output_text(outputs, mode: OutputMode) -> str | None:  # type: ignore[no-untyped-def]
    if mode is OutputMode.CANONICAL_JSON:
        return (
            json.dumps(outputs.canonical_json, indent=2)
            if outputs.canonical_json is not None
            else None
        )
    return {
        OutputMode.BLOCK4: outputs.block4,
        OutputMode.FIN: outputs.fin,
        OutputMode.TXT: outputs.txt,
        OutputMode.XML: outputs.xml,
        OutputMode.APPHDR: outputs.app_hdr,
        OutputMode.DOCUMENT: outputs.document,
    }.get(mode)
