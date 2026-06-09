import base64
import binascii
import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import UTC
from datetime import date
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Literal

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import ValidationError
from pydantic import create_model

from app.core.config import settings
from app.core.exceptions import FormNotFound
from app.core.exceptions import FormStateError
from app.core.exceptions import ResponseValidationError
from app.models.form import FieldType
from app.models.form import Form
from app.models.form import FormField
from app.models.form import FormStatus
from app.models.response import DraftResponse
from app.models.response import Response
from app.repositories.files_repo import FilesRepository
from app.repositories.forms_repo import FormsRepository
from app.repositories.responses_repo import ResponsesRepository
from app.schemas.response import ExportFormat


# Basic email shape; full RFC validation is out of scope (no email-validator dep).
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _base_and_constraints(field: FormField) -> tuple[Any, dict[str, Any]]:
    """Map a form field to a Python type + Pydantic constraints from its validation."""
    v = field.validation
    constraints: dict[str, Any] = {}
    match field.type:
        case FieldType.SHORT_TEXT | FieldType.LONG_TEXT:
            base: Any = str
            if v:
                if v.min_length is not None:
                    constraints["min_length"] = v.min_length
                if v.max_length is not None:
                    constraints["max_length"] = v.max_length
                if v.regex:
                    constraints["pattern"] = v.regex
        case FieldType.EMAIL:
            base = str
            constraints["pattern"] = _EMAIL_PATTERN
        case FieldType.NUMBER:
            base = int | float
            if v:
                if v.min is not None:
                    constraints["ge"] = v.min
                if v.max is not None:
                    constraints["le"] = v.max
        case FieldType.RATING:
            base = int
            if v:
                if v.min is not None:
                    constraints["ge"] = v.min
                if v.max is not None:
                    constraints["le"] = v.max
        case FieldType.DATE:
            base = date
        case FieldType.SINGLE_CHOICE:
            base = Literal[tuple(field.options or ())]
        case FieldType.MULTI_CHOICE:
            base = list[Literal[tuple(field.options or ())]]
        case FieldType.FILE:
            # Stored file_id; GridFS existence is verified in the files step.
            base = str
    return base, constraints


def _field_definition(field: FormField, *, partial: bool) -> tuple[Any, Any]:
    base, constraints = _base_and_constraints(field)
    if field.required and not partial:
        return base, Field(**constraints)
    return base | None, Field(default=None, **constraints)


def build_answer_model(
    fields: list[FormField],
    *,
    partial: bool = False,
) -> type[BaseModel]:
    """Build a Pydantic model at runtime from a form's field definitions.

    Unknown keys are rejected (extra='forbid') so respondents cannot smuggle
    arbitrary data into the stored document. With partial=True every field is
    optional (draft saves), but provided values are still type-checked.
    """
    definitions: dict[str, Any] = {
        field.key: _field_definition(field, partial=partial) for field in fields
    }
    return create_model(
        "DynamicAnswerModel",
        __config__=ConfigDict(extra="forbid"),
        **definitions,
    )


def _format_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in exc.errors(include_url=False)
    ]


def _validate_answers(
    fields: list[FormField], answers: dict[str, Any], *, partial: bool = False
) -> dict[str, Any]:
    model = build_answer_model(fields, partial=partial)
    try:
        validated = model.model_validate(answers)
    except ValidationError as exc:
        raise ResponseValidationError(_format_errors(exc)) from exc
    return validated.model_dump(mode="json")


def _encode_cursor(response: Response) -> str:
    """Opaque keyset cursor carrying the last response's (submitted_at, _id)."""
    raw = f"{response.submitted_at.isoformat()}|{response.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[datetime, ObjectId] | None:
    """Parse a cursor back into its sort keys; a malformed cursor pages from start."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        submitted_at, oid = raw.rsplit("|", 1)
        return datetime.fromisoformat(submitted_at), ObjectId(oid)
    except (ValueError, binascii.Error, InvalidId):
        return None


def _csv_cell(value: Any) -> str:
    """Render one answer value as a CSV cell; non-scalars become compact JSON."""
    if value is None:
        return ""
    if isinstance(value, str | int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def _csv_row(values: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(values)
    return buf.getvalue()


async def _csv_stream(
    field_keys: list[str],
    rows: AsyncIterator[Response],
) -> AsyncIterator[str]:
    yield _csv_row(["id", "submitted_at", *field_keys])
    async for response in rows:
        answers = {a.key: a.value for a in response.answers}
        cells = [_csv_cell(answers.get(key)) for key in field_keys]
        yield _csv_row([str(response.id), response.submitted_at.isoformat(), *cells])


async def _json_stream(rows: AsyncIterator[Response]) -> AsyncIterator[str]:
    yield "["
    first = True
    async for response in rows:
        item = {
            "id": str(response.id),
            "form_version": response.form_version,
            "submitted_at": response.submitted_at.isoformat(),
            "answers": {a.key: a.value for a in response.answers},
        }
        yield ("" if first else ",") + json.dumps(item, ensure_ascii=False, default=str)
        first = False
    yield "]"


class ResponseService:
    def __init__(
        self,
        forms: FormsRepository,
        responses: ResponsesRepository,
        files: FilesRepository,
    ) -> None:
        self._forms = forms
        self._responses = responses
        self._files = files

    async def get_public_form(self, form_id: ObjectId) -> Form:
        form = await self._forms.get_by_id(form_id)
        # Drafts are not publicly visible; treat as not found to avoid disclosure.
        if form is None or form.status == FormStatus.DRAFT:
            raise FormNotFound
        return form

    async def list_for_owner(
        self,
        form_id: ObjectId,
        owner_id: ObjectId,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Response], str | None]:
        form = await self._forms.get_by_id(form_id)
        # Not-found and not-owned both map to 404 so form existence is not disclosed.
        if form is None or form.owner_id != owner_id:
            raise FormNotFound
        responses = await self._responses.list_by_form(
            form_id,
            limit,
            _decode_cursor(cursor),
        )
        next_cursor = _encode_cursor(responses[-1]) if len(responses) == limit else None
        return responses, next_cursor

    async def export(
        self, form_id: ObjectId, owner_id: ObjectId, fmt: ExportFormat
    ) -> tuple[str, str, AsyncIterator[str]]:
        """Validate ownership, then return (media_type, filename, row stream).

        Ownership is checked before any row is read so a rejection surfaces as a
        normal 404 instead of an error mid-stream.
        """
        form = await self._forms.get_by_id(form_id)
        # Not-found and not-owned both map to 404 so form existence is not disclosed.
        if form is None or form.owner_id != owner_id:
            raise FormNotFound
        rows = self._responses.iter_by_form(form_id)
        if fmt == ExportFormat.CSV:
            field_keys = [field.key for field in form.fields]
            return "text/csv", f"form_{form_id}.csv", _csv_stream(field_keys, rows)
        return "application/json", f"form_{form_id}.json", _json_stream(rows)

    async def _load_accepting_form(self, form_id: ObjectId) -> Form:
        """Load a form that anonymous users may submit to, or raise."""
        form = await self._forms.get_by_id(form_id)
        if form is None or form.status == FormStatus.DRAFT:
            raise FormNotFound
        if form.status == FormStatus.CLOSED or not form.settings.accepting_responses:
            raise FormStateError("Form is not accepting responses")
        return form

    async def submit(
        self, form_id: ObjectId, answers: dict[str, Any], meta: dict[str, Any]
    ) -> Response:
        form = await self._load_accepting_form(form_id)

        validated = _validate_answers(form.fields, answers)
        validated = await self._resolve_files(form_id, form.fields, validated)
        stored = [{"key": k, "value": v} for k, v in validated.items() if v is not None]
        return await self._responses.create(
            form_id=form_id,
            form_version=form.version,
            answers=stored,
            meta=meta,
        )

    async def save_draft(
        self,
        form_id: ObjectId,
        answers: dict[str, Any],
    ) -> DraftResponse:
        """Persist a partial answer that expires (TTL) unless submitted in time."""
        form = await self._load_accepting_form(form_id)

        validated = _validate_answers(form.fields, answers, partial=True)
        stored = [{"key": k, "value": v} for k, v in validated.items() if v is not None]
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.draft_ttl_seconds)
        return await self._responses.create_draft(
            form_id=form_id,
            answers=stored,
            expires_at=expires_at,
        )

    async def _resolve_files(
        self,
        form_id: ObjectId,
        fields: list[FormField],
        validated: dict[str, Any],
    ) -> dict[str, Any]:
        """Replace each file field's id with {file_id, filename, size}.

        The referenced file must exist in GridFS and belong to this form,
        otherwise the submission is rejected as invalid (422).
        """
        errors: list[dict[str, Any]] = []
        for field in fields:
            if field.type != FieldType.FILE:
                continue
            value = validated.get(field.key)
            if value is None:
                continue
            resolved = await self._resolve_file(form_id, value)
            if resolved is None:
                errors.append(
                    {
                        "loc": [field.key],
                        "msg": "Unknown or invalid file reference",
                        "type": "value_error",
                    }
                )
            else:
                validated[field.key] = resolved
        if errors:
            raise ResponseValidationError(errors)
        return validated

    async def _resolve_file(
        self,
        form_id: ObjectId,
        value: Any,
    ) -> dict[str, Any] | None:
        if not ObjectId.is_valid(value):
            return None
        file_id = ObjectId(value)
        grid_out = await self._files.open(file_id)
        if grid_out is None:
            return None
        # Reject files uploaded for a different form to prevent cross-form references.
        if (grid_out.metadata or {}).get("form_id") != form_id:
            return None
        return {"file_id": file_id, "filename": grid_out.filename, "size": grid_out.length}
