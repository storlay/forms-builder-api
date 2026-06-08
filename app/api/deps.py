from typing import Annotated

import jwt
from bson import ObjectId
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security import HTTPBearer

from app.core.db import DbDep
from app.core.exceptions import FileNotFound
from app.core.exceptions import FormNotFound
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.files_repo import FilesRepository
from app.repositories.forms_repo import FormsRepository
from app.repositories.responses_repo import ResponsesRepository
from app.repositories.users_repo import UsersRepository
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.form_service import FormService
from app.services.response_service import ResponseService


_bearer = HTTPBearer(auto_error=False)


def get_auth_service(db: DbDep) -> AuthService:
    return AuthService(UsersRepository(db))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_form_service(db: DbDep) -> FormService:
    return FormService(FormsRepository(db))


FormServiceDep = Annotated[FormService, Depends(get_form_service)]


def get_response_service(db: DbDep) -> ResponseService:
    return ResponseService(
        FormsRepository(db),
        ResponsesRepository(db),
        FilesRepository(db),
    )


ResponseServiceDep = Annotated[ResponseService, Depends(get_response_service)]


def get_file_service(db: DbDep) -> FileService:
    return FileService(FormsRepository(db), FilesRepository(db))


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


def get_analytics_service(db: DbDep) -> AnalyticsService:
    return AnalyticsService(FormsRepository(db), ResponsesRepository(db))


AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]


def parse_form_id(form_id: str) -> ObjectId:
    if not ObjectId.is_valid(form_id):
        raise FormNotFound
    return ObjectId(form_id)


FormId = Annotated[ObjectId, Depends(parse_form_id)]


def parse_file_id(file_id: str) -> ObjectId:
    if not ObjectId.is_valid(file_id):
        raise FileNotFound
    return ObjectId(file_id)


FileId = Annotated[ObjectId, Depends(parse_file_id)]


async def get_current_user(
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise credentials_exc
    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise credentials_exc from None

    user = await UsersRepository(db).get_by_id(ObjectId(user_id))
    if user is None:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
