from typing import TYPE_CHECKING

from pymongo.errors import DuplicateKeyError

from app.core.exceptions import EmailAlreadyExists
from app.core.exceptions import InvalidCredentials
from app.core.security import create_access_token
from app.core.security import hash_password
from app.core.security import verify_password


if TYPE_CHECKING:
    from pydantic import EmailStr

    from app.models.user import User
    from app.repositories.users_repo import UsersRepository


class AuthService:
    def __init__(self, users: "UsersRepository") -> None:
        self._users = users

    async def register(self, email: "EmailStr", password: str) -> "User":
        try:
            return await self._users.create(email, hash_password(password))
        except DuplicateKeyError as e:
            raise EmailAlreadyExists from e

    async def authenticate(self, email: str, password: str) -> str:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentials
        return create_access_token(str(user.id))
