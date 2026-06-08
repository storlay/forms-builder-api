from datetime import UTC
from datetime import datetime
from typing import Any

from bson import ObjectId

from app.core.exceptions import FormNotFound
from app.core.exceptions import FormStateError
from app.models.form import Form
from app.models.form import FormField
from app.models.form import FormStatus
from app.repositories.forms_repo import FormsRepository
from app.schemas.form import FieldRequest
from app.schemas.form import FormCreateRequest
from app.schemas.form import FormUpdateRequest


def _serialize_fields(fields: list[FieldRequest]) -> list[dict[str, Any]]:
    """DTO fields -> storage dicts, assigning a stable order by position."""
    return [{**field.model_dump(mode="json"), "order": i} for i, field in enumerate(fields)]


def _dump_fields(fields: list[FormField]) -> list[dict[str, Any]]:
    return [field.model_dump(mode="json") for field in fields]


class FormService:
    def __init__(self, forms: FormsRepository) -> None:
        self._forms = forms

    async def create(self, owner_id: ObjectId, payload: FormCreateRequest) -> Form:
        return await self._forms.create(
            owner_id=owner_id,
            title=payload.title,
            description=payload.description,
            fields=_serialize_fields(payload.fields),
            settings=payload.settings.model_dump(),
        )

    async def list_for_owner(
        self, owner_id: ObjectId, limit: int, cursor: ObjectId | None
    ) -> list[Form]:
        return await self._forms.list_by_owner(owner_id, limit, cursor)

    async def get_owned(self, form_id: ObjectId, owner_id: ObjectId) -> Form:
        form = await self._forms.get_by_id(form_id)
        # Not-found and not-owned both map to 404 so form existence is not disclosed.
        if form is None or form.owner_id != owner_id:
            raise FormNotFound
        return form

    async def update(
        self, form_id: ObjectId, owner_id: ObjectId, payload: FormUpdateRequest
    ) -> Form:
        form = await self.get_owned(form_id, owner_id)
        if form.status == FormStatus.CLOSED:
            raise FormStateError("Closed form cannot be edited")

        changes = payload.model_dump(exclude_unset=True)
        schema_changed = "fields" in changes
        if schema_changed:
            changes["fields"] = _serialize_fields(payload.fields)
        if "settings" in changes:
            changes["settings"] = payload.settings.model_dump()

        # A published form is frozen: editing its schema forks a new version + snapshot.
        # Editing only metadata (title/description/settings) keeps the version.
        if form.status == FormStatus.PUBLISHED and schema_changed:
            new_version = form.version + 1
            changes["version"] = new_version
            updated = await self._forms.update(form_id, changes)
            await self._forms.add_version_snapshot(
                form_id,
                new_version,
                changes["fields"],
            )
            return updated

        return await self._forms.update(form_id, changes)

    async def publish(self, form_id: ObjectId, owner_id: ObjectId) -> Form:
        form = await self.get_owned(form_id, owner_id)
        if form.status != FormStatus.DRAFT:
            raise FormStateError("Only draft forms can be published")
        if not form.fields:
            raise FormStateError("Cannot publish a form without fields")

        updated = await self._forms.update(
            form_id,
            {"status": FormStatus.PUBLISHED.value, "published_at": datetime.now(UTC)},
        )
        await self._forms.add_version_snapshot(
            form_id,
            form.version,
            _dump_fields(form.fields),
        )
        return updated

    async def close(self, form_id: ObjectId, owner_id: ObjectId) -> Form:
        form = await self.get_owned(form_id, owner_id)
        if form.status != FormStatus.PUBLISHED:
            raise FormStateError("Only published forms can be closed")
        return await self._forms.update(form_id, {"status": FormStatus.CLOSED.value})

    async def delete(self, form_id: ObjectId, owner_id: ObjectId) -> None:
        await self.get_owned(form_id, owner_id)
        await self._forms.delete(form_id)
