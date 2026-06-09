from fastapi import APIRouter

from app.api.deps import AnalyticsServiceDep
from app.api.deps import CurrentUser
from app.api.deps import FormId
from app.schemas.analytics import FormAnalyticsResponse


router = APIRouter(
    prefix="/forms",
    tags=["analytics"],
)


@router.get(
    "/{form_id}/analytics",
    response_model=FormAnalyticsResponse,
)
async def form_analytics(
    form_id: FormId,
    user: CurrentUser,
    service: AnalyticsServiceDep,
) -> FormAnalyticsResponse:
    return await service.get_summary(form_id, user.id)
