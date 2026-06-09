import hashlib
from typing import Annotated

from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser
from app.api.deps import FormId
from app.api.deps import RateLimited
from app.api.deps import ResponseServiceDep
from app.schemas.response import DraftRequest
from app.schemas.response import DraftResult
from app.schemas.response import ExportFormat
from app.schemas.response import PublicFormResponse
from app.schemas.response import ResponseItem
from app.schemas.response import ResponseListResponse
from app.schemas.response import SubmitRequest
from app.schemas.response import SubmitResult


router = APIRouter(tags=["responses"])


def _build_meta(request: Request) -> dict[str, str]:
    """Anonymous request metadata: IP is hashed, no PII stored."""
    host = request.client.host if request.client else ""
    return {
        "ip_hash": hashlib.sha256(host.encode()).hexdigest(),
        "user_agent": request.headers.get("user-agent", ""),
    }


@router.get(
    "/f/{form_id}",
    response_model=PublicFormResponse,
)
async def get_public_form(
    form_id: FormId,
    service: ResponseServiceDep,
) -> PublicFormResponse:
    form = await service.get_public_form(form_id)
    return PublicFormResponse.model_validate(form)


@router.post(
    "/f/{form_id}/responses",
    response_model=SubmitResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[RateLimited],
)
async def submit_response(
    form_id: FormId,
    payload: SubmitRequest,
    request: Request,
    service: ResponseServiceDep,
) -> SubmitResult:
    response = await service.submit(
        form_id,
        payload.answers,
        _build_meta(request),
    )
    return SubmitResult.model_validate(response)


@router.get(
    "/forms/{form_id}/responses",
    response_model=ResponseListResponse,
)
async def list_responses(
    form_id: FormId,
    user: CurrentUser,
    service: ResponseServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> ResponseListResponse:
    responses, next_cursor = await service.list_for_owner(
        form_id,
        user.id,
        limit,
        cursor,
    )
    return ResponseListResponse(
        items=[ResponseItem.model_validate(r) for r in responses],
        next_cursor=next_cursor,
    )


@router.get("/forms/{form_id}/export")
async def export_responses(
    form_id: FormId,
    user: CurrentUser,
    service: ResponseServiceDep,
    export_format: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.CSV,
) -> StreamingResponse:
    media_type, filename, stream = await service.export(
        form_id,
        user.id,
        export_format,
    )
    return StreamingResponse(
        stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/f/{form_id}/draft",
    response_model=DraftResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[RateLimited],
)
async def save_draft(
    form_id: FormId,
    payload: DraftRequest,
    service: ResponseServiceDep,
) -> DraftResult:
    draft = await service.save_draft(
        form_id,
        payload.answers,
    )
    return DraftResult.model_validate(draft)
