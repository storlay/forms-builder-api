from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

from app.models.user import User


if TYPE_CHECKING:
    from bson import ObjectId
    from pydantic import EmailStr
    from pymongo.asynchronous.database import AsyncDatabase


class UsersRepository:
    def __init__(self, db: "AsyncDatabase") -> None:
        self._col = db.users

    async def get_by_email(self, email: str) -> User | None:
        doc = await self._col.find_one({"email": email})
        return User.model_validate(doc) if doc else None

    async def get_by_id(self, user_id: "ObjectId") -> User | None:
        doc = await self._col.find_one({"_id": user_id})
        return User.model_validate(doc) if doc else None

    async def create(self, email: "EmailStr", password_hash: str) -> User:
        doc = {
            "email": email,
            "password_hash": password_hash,
            "created_at": datetime.now(UTC),
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return User.model_validate(doc)
