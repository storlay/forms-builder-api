from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter
from fastapi import Query
from fastapi import status

from app.api.deps import CurrentUser
from app.api.deps import FormId
from app.api.deps import FormServiceDep
from app.schemas.form import FormCreateRequest
from app.schemas.form import FormListResponse
from app.schemas.form import FormResponse
from app.schemas.form import FormUpdateRequest


router = APIRouter(
    prefix="/forms",
    tags=["forms"],
)


@router.post(
    "",
    response_model=FormResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_form(
    payload: FormCreateRequest,
    user: CurrentUser,
    service: FormServiceDep,
) -> FormResponse:
    form = await service.create(user.id, payload)
    return FormResponse.model_validate(form)


@router.get(
    "",
    response_model=FormListResponse,
)
async def list_forms(
    user: CurrentUser,
    service: FormServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> FormListResponse:
    cursor_id = ObjectId(cursor) if cursor and ObjectId.is_valid(cursor) else None
    forms = await service.list_for_owner(user.id, limit, cursor_id)
    next_cursor = str(forms[-1].id) if len(forms) == limit else None
    return FormListResponse(
        items=[FormResponse.model_validate(form) for form in forms],
        next_cursor=next_cursor,
    )


@router.get(
    "/{form_id}",
    response_model=FormResponse,
)
async def get_form(
    form_id: FormId,
    user: CurrentUser,
    service: FormServiceDep,
) -> FormResponse:
    form = await service.get_owned(form_id, user.id)
    return FormResponse.model_validate(form)


@router.patch(
    "/{form_id}",
    response_model=FormResponse,
)
async def update_form(
    form_id: FormId,
    payload: FormUpdateRequest,
    user: CurrentUser,
    service: FormServiceDep,
) -> FormResponse:
    form = await service.update(form_id, user.id, payload)
    return FormResponse.model_validate(form)


@router.post("/{form_id}/publish", response_model=FormResponse)
async def publish_form(
    form_id: FormId,
    user: CurrentUser,
    service: FormServiceDep,
) -> FormResponse:
    form = await service.publish(form_id, user.id)
    return FormResponse.model_validate(form)


@router.post("/{form_id}/close", response_model=FormResponse)
async def close_form(
    form_id: FormId,
    user: CurrentUser,
    service: FormServiceDep,
) -> FormResponse:
    form = await service.close(form_id, user.id)
    return FormResponse.model_validate(form)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(
    form_id: FormId,
    user: CurrentUser,
    service: FormServiceDep,
) -> None:
    await service.delete(form_id, user.id)
