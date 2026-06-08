from datetime import UTC
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.models.form import Form
from app.models.form import FormStatus


class FormsRepository:
    def __init__(self, db: AsyncDatabase) -> None:
        self._forms = db.forms
        self._versions = db.form_versions

    async def create(
        self,
        *,
        owner_id: ObjectId,
        title: str,
        description: str,
        fields: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> Form:
        now = datetime.now(UTC)
        doc = {
            "owner_id": owner_id,
            "title": title,
            "description": description,
            "status": FormStatus.DRAFT.value,
            "version": 1,
            "fields": fields,
            "settings": settings,
            "created_at": now,
            "updated_at": now,
            "published_at": None,
        }
        result = await self._forms.insert_one(doc)
        doc["_id"] = result.inserted_id
        return Form.model_validate(doc)

    async def get_by_id(self, form_id: ObjectId) -> Form | None:
        doc = await self._forms.find_one({"_id": form_id})
        return Form.model_validate(doc) if doc else None

    async def list_by_owner(
        self, owner_id: ObjectId, limit: int, cursor: ObjectId | None
    ) -> list[Form]:
        query: dict[str, Any] = {"owner_id": owner_id}
        if cursor is not None:
            query["_id"] = {"$lt": cursor}
        cursor_iter = self._forms.find(query).sort("_id", DESCENDING).limit(limit)
        return [Form.model_validate(doc) async for doc in cursor_iter]

    async def update(self, form_id: ObjectId, changes: dict[str, Any]) -> Form:
        changes["updated_at"] = datetime.now(UTC)
        doc = await self._forms.find_one_and_update(
            {"_id": form_id}, {"$set": changes}, return_document=ReturnDocument.AFTER
        )
        return Form.model_validate(doc)

    async def delete(self, form_id: ObjectId) -> None:
        await self._forms.delete_one({"_id": form_id})
        await self._versions.delete_many({"form_id": form_id})

    async def add_version_snapshot(
        self, form_id: ObjectId, version: int, fields: list[dict[str, Any]]
    ) -> None:
        await self._versions.insert_one(
            {
                "form_id": form_id,
                "version": version,
                "fields": fields,
                "created_at": datetime.now(UTC),
            }
        )
