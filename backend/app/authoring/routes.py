from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.authoring.models import (
    ApprovalResponse,
    AuditEventResponse,
    ComposeResponse,
    ConnectorSummary,
    DevelopmentLoginRequest,
    DownloadFormat,
    DraftCreateRequest,
    DraftResponse,
    DraftStatus,
    DraftUpdateRequest,
    ExternalValidationImportRequest,
    FieldUpsertRequest,
    FinEnvelopeRequest,
    MessageImportRequest,
    MessageImportResponse,
    OutputMode,
    PlatformRole,
    ReviewResponse,
    SequenceCreateRequest,
    SessionResponse,
    SessionUser,
    SubmissionRequest,
    SubmissionResponse,
    UnsupportedImportField,
)
from app.authoring.operations import OperationsService
from app.authoring.parser import parse_supported_message
from app.authoring.service import AuthoringService
from app.config import Settings, get_settings
from app.samples.service import sample_service
from app.security.auth import (
    SessionService,
    get_current_user,
    get_session_service,
    require_csrf,
)
from app.specifications.registry import specification_registry

router = APIRouter(prefix="/api")


def _authoring(settings: Settings) -> AuthoringService:
    if not settings.real_data_mode_enabled:
        raise HTTPException(status_code=503, detail="Secure real-data authoring is disabled")
    return AuthoringService(settings)


def _require(user: SessionUser, *roles: PlatformRole) -> None:
    if not user.roles.intersection(roles):
        raise HTTPException(status_code=403, detail="Role is not authorised")


@router.post("/auth/development-login", response_model=SessionResponse)
def development_login(
    payload: DevelopmentLoginRequest,
    response: Response,
    service: Annotated[SessionService, Depends(get_session_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    issued = service.development_login(payload.identity)
    response.set_cookie(
        settings.session_cookie_name,
        issued.token,
        httponly=True,
        secure=settings.session_secure_cookies,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        issued.csrf_token,
        httponly=False,
        secure=settings.session_secure_cookies,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return SessionResponse(
        authenticated=True,
        user=issued.user,
        auth_mode=settings.auth_mode,
        expires_at=issued.expires_at,
    )


@router.get("/auth/session", response_model=SessionResponse)
def current_session(
    request: Request,
    service: Annotated[SessionService, Depends(get_session_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionResponse:
    authenticated = service.authenticate(request.cookies.get(settings.session_cookie_name))
    if authenticated is None:
        return SessionResponse(authenticated=False, auth_mode=settings.auth_mode)
    user, expires_at = authenticated
    return SessionResponse(
        authenticated=True,
        user=user,
        auth_mode=settings.auth_mode,
        expires_at=expires_at,
    )


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: Annotated[SessionUser, Depends(require_csrf)],
    service: Annotated[SessionService, Depends(get_session_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    del user
    service.logout(request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    response.status_code = 204
    return response


@router.post("/messages/drafts", response_model=DraftResponse)
def create_draft(
    payload: DraftCreateRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.create_draft(
        user, payload.message_type, payload.profile_id
    )


@router.post("/knowledge/samples/{sample_id}/load", response_model=DraftResponse)
def load_sample_into_draft(
    sample_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    sample = sample_service.get(sample_id)
    authoring = _authoring(settings)
    draft = authoring.repository.create_draft(user, sample.message_type, sample.profile_id)
    specification = specification_registry.get(sample.message_type)
    sequence_specs = {item.path: item for item in specification.sequences}

    def sequence_map(current: DraftResponse) -> dict[tuple[str, int], str]:
        return {
            (item.sequence_path, item.occurrence): item.sequence_id for item in current.sequences
        }

    for annotation in sample.annotations:
        mapped = sequence_map(draft)
        key = (annotation.sequence_path, annotation.sequence_occurrence)
        if key not in mapped:
            sequence_spec = sequence_specs[annotation.sequence_path]
            parent_id = None
            if sequence_spec.parent_path:
                parent_id = mapped.get((sequence_spec.parent_path, 1))
                if parent_id is None:
                    raise ValueError("The sample has an unresolved parent sequence")
            draft = authoring.repository.add_sequence(
                user, draft.draft_id, annotation.sequence_path, parent_id
            )
            mapped = sequence_map(draft)
        draft = authoring.repository.upsert_field(
            user,
            draft.draft_id,
            FieldUpsertRequest(
                row_id=annotation.row_id,
                sequence_id=mapped[key],
                value=annotation.entered_value,
                source="SAMPLE_DATA",
                confirmed=False,
            ),
        )
    return draft


@router.post("/messages/import", response_model=MessageImportResponse)
def import_supported_message(
    payload: MessageImportRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageImportResponse:
    _require(user, PlatformRole.AUTHOR)
    parsed = parse_supported_message(payload.raw_message, specification_registry.get)
    authoring = _authoring(settings)
    draft = authoring.repository.create_draft(user, parsed.message_type, payload.profile_id)
    specification = specification_registry.get(parsed.message_type)
    sequence_specs = {item.path: item for item in specification.sequences}

    def sequence_map(current: DraftResponse) -> dict[tuple[str, int], str]:
        return {
            (item.sequence_path, item.occurrence): item.sequence_id for item in current.sequences
        }

    for parsed_field in parsed.fields:
        mapped = sequence_map(draft)
        key = (parsed_field.sequence_path, parsed_field.sequence_occurrence)
        if key not in mapped:
            sequence_spec = sequence_specs[parsed_field.sequence_path]
            parent_id = None
            if sequence_spec.parent_path:
                parent_id = mapped.get((sequence_spec.parent_path, 1))
                if parent_id is None:
                    raise ValueError("The imported field has an unresolved parent sequence")
            draft = authoring.repository.add_sequence(
                user, draft.draft_id, parsed_field.sequence_path, parent_id
            )
            mapped = sequence_map(draft)
        draft = authoring.repository.upsert_field(
            user,
            draft.draft_id,
            FieldUpsertRequest(
                row_id=parsed_field.row.row_id,
                sequence_id=mapped[key],
                value=parsed_field.value,
                source="IMPORTED_API",
                confirmed=False,
            ),
        )
    composition = authoring.compose(user, draft.draft_id)
    return MessageImportResponse(
        draft=authoring.get_draft(user, draft.draft_id),
        composition=composition,
        unsupported_fields=[
            UnsupportedImportField(
                line_number=item.line_number,
                raw_line=item.raw_line,
                reason=item.reason,
            )
            for item in parsed.unsupported
        ],
        original_checksum=parsed.checksum,
        round_trip_equivalent=(composition.block_4 == parsed.block_4),
    )


@router.get("/messages/drafts/{draft_id}", response_model=DraftResponse)
def get_draft(
    draft_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(
        user,
        PlatformRole.VIEWER,
        PlatformRole.AUTHOR,
        PlatformRole.REVIEWER,
        PlatformRole.APPROVER,
        PlatformRole.SUBMITTER,
        PlatformRole.AUDITOR,
    )
    return _authoring(settings).get_draft(user, draft_id)


@router.patch("/messages/drafts/{draft_id}", response_model=DraftResponse)
def update_draft(
    draft_id: str,
    payload: DraftUpdateRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.update_profile(user, draft_id, payload.profile_id)


@router.post("/messages/drafts/{draft_id}/sequences", response_model=DraftResponse)
def add_sequence(
    draft_id: str,
    payload: SequenceCreateRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.add_sequence(
        user, draft_id, payload.sequence_path, payload.parent_sequence_id
    )


@router.delete("/messages/drafts/{draft_id}/sequences/{sequence_id}", response_model=DraftResponse)
def remove_sequence(
    draft_id: str,
    sequence_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.remove_sequence(user, draft_id, sequence_id)


@router.post("/messages/drafts/{draft_id}/fields", response_model=DraftResponse)
def upsert_field(
    draft_id: str,
    payload: FieldUpsertRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.upsert_field(user, draft_id, payload)


@router.delete("/messages/drafts/{draft_id}/fields/{field_id}", response_model=DraftResponse)
def remove_field(
    draft_id: str,
    field_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DraftResponse:
    _require(user, PlatformRole.AUTHOR)
    return _authoring(settings).repository.delete_field(user, draft_id, field_id)


@router.post("/messages/{draft_id}/compose")
def compose_draft(
    draft_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ComposeResponse:
    _require(user, PlatformRole.AUTHOR, PlatformRole.REVIEWER, PlatformRole.APPROVER)
    return _authoring(settings).compose(user, draft_id)


@router.post("/messages/{draft_id}/validate")
def validate_draft(
    draft_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ComposeResponse:
    _require(user, PlatformRole.AUTHOR, PlatformRole.REVIEWER, PlatformRole.APPROVER)
    return _authoring(settings).compose(user, draft_id)


@router.post("/messages/{draft_id}/review", response_model=ReviewResponse)
def request_review(
    draft_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewResponse:
    _require(user, PlatformRole.AUTHOR)
    draft = _authoring(settings).repository.request_review(user, draft_id)
    return ReviewResponse(
        draft_id=draft.id,
        status=DraftStatus(draft.status),
        revision=draft.revision,
    )


@router.post("/messages/{draft_id}/approve", response_model=ApprovalResponse)
def approve_draft(
    draft_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApprovalResponse:
    _require(user, PlatformRole.APPROVER)
    approval = _authoring(settings).repository.approve(user, draft_id)
    return ApprovalResponse(
        draft_id=approval.draft_id,
        status=DraftStatus.APPROVED,
        revision=approval.revision,
        approved_by=approval.approved_by,
        checksum=approval.message_checksum,
    )


@router.get("/messages/{draft_id}/downloads")
def list_downloads(
    draft_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    _authoring(settings).get_draft(user, draft_id)
    return {
        "draftId": draft_id,
        "formats": [item.value for item in DownloadFormat],
        "finEnabled": settings.fin_export_enabled,
        "rjeEnabled": settings.rje_export_enabled,
    }


@router.get("/messages/{draft_id}/downloads/{download_format}")
def download_message(
    draft_id: str,
    download_format: DownloadFormat,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    _require(user, PlatformRole.AUTHOR, PlatformRole.REVIEWER, PlatformRole.APPROVER)
    if download_format in {DownloadFormat.FIN, DownloadFormat.RJE}:
        raise ValueError("FIN/RJE envelope values must be sent in the protected POST export body")
    artifact = _authoring(settings).download(user, draft_id, download_format, None)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.post("/messages/{draft_id}/exports/{download_format}")
def export_enveloped_message(
    draft_id: str,
    download_format: DownloadFormat,
    payload: FinEnvelopeRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    _require(user, PlatformRole.AUTHOR, PlatformRole.REVIEWER, PlatformRole.APPROVER)
    expected_mode = {
        DownloadFormat.FIN: OutputMode.FIN_APPLICATION_MESSAGE,
        DownloadFormat.RJE: OutputMode.RJE_SINGLE,
    }.get(download_format)
    if expected_mode is None or payload.output_mode is not expected_mode:
        raise ValueError("The output mode does not match the requested envelope format")
    artifact = _authoring(settings).download(user, draft_id, download_format, payload)
    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@router.get("/messages/{draft_id}/audit", response_model=list[AuditEventResponse])
def message_audit(
    draft_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AuditEventResponse]:
    _require(
        user,
        PlatformRole.AUTHOR,
        PlatformRole.REVIEWER,
        PlatformRole.APPROVER,
        PlatformRole.AUDITOR,
    )
    return _authoring(settings).repository.list_audit(user, draft_id)


@router.get("/connectors", response_model=list[ConnectorSummary])
def list_connectors(
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ConnectorSummary]:
    operations = OperationsService(settings, _authoring(settings), _authoring(settings).repository)
    return operations.list_connectors(user)


@router.get("/connectors/{connector_id}/health")
def connector_health(
    connector_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    operations = OperationsService(settings, _authoring(settings), _authoring(settings).repository)
    return operations.connector_health(user, connector_id)


@router.post("/connectors/{connector_id}/test")
def test_connector(
    connector_id: str,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    _require(user, PlatformRole.SECURITY_ADMIN)
    authoring = _authoring(settings)
    return OperationsService(settings, authoring, authoring.repository).test_connector(
        user, connector_id
    )


@router.post("/messages/{draft_id}/submit", response_model=SubmissionResponse)
def submit_message(
    draft_id: str,
    payload: SubmissionRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SubmissionResponse:
    _require(user, PlatformRole.SUBMITTER)
    authoring = _authoring(settings)
    return OperationsService(settings, authoring, authoring.repository).submit(
        user, draft_id, payload
    )


@router.get("/messages/{draft_id}/submissions", response_model=list[SubmissionResponse])
def list_submissions(
    draft_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SubmissionResponse]:
    _require(user, PlatformRole.SUBMITTER, PlatformRole.AUDITOR, PlatformRole.APPROVER)
    authoring = _authoring(settings)
    return OperationsService(settings, authoring, authoring.repository).submissions(user, draft_id)


@router.post("/external-validation/results/{draft_id}", status_code=201)
def import_external_validation(
    draft_id: str,
    payload: ExternalValidationImportRequest,
    user: Annotated[SessionUser, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    _require(user, PlatformRole.REVIEWER, PlatformRole.APPROVER)
    authoring = _authoring(settings)
    validation_id = OperationsService(
        settings, authoring, authoring.repository
    ).import_external_validation(user, draft_id, payload)
    return {"validationId": validation_id}


@router.get("/external-validation/results/{draft_id}")
def list_external_validation(
    draft_id: str,
    user: Annotated[SessionUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[dict[str, object]]:
    authoring = _authoring(settings)
    return OperationsService(settings, authoring, authoring.repository).external_validations(
        user, draft_id
    )
