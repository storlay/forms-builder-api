from fastapi import APIRouter
from fastapi import status

from app.api.deps import AuthServiceDep
from app.api.deps import CurrentUser
from app.schemas.auth import LoginRequest
from app.schemas.auth import RegisterRequest
from app.schemas.auth import TokenResponse
from app.schemas.auth import UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    service: AuthServiceDep,
) -> UserResponse:
    user = await service.register(
        payload.email,
        payload.password,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    payload: LoginRequest,
    service: AuthServiceDep,
) -> TokenResponse:
    token = await service.authenticate(payload.email, payload.password)
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
