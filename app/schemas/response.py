from datetime import datetime
from enum import StrEnum
from typing import Any

from bson import ObjectId
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_serializer

from app.models.py_object_id import PyObjectId
from app.schemas.form import FieldResponse


def _jsonable(value: Any) -> Any:
    """Stringify ObjectId nested in a dynamic answer value (e.g. file refs)."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


class ExportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"


class SubmitRequest(BaseModel):
    answers: dict[str, Any]


class SubmitResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PyObjectId
    form_version: int
    submitted_at: datetime


class DraftRequest(BaseModel):
    answers: dict[str, Any]


class DraftResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PyObjectId
    expires_at: datetime


class AnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any

    @field_serializer("value")
    def _serialize_value(self, value: Any) -> Any:
        return _jsonable(value)


class ResponseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PyObjectId
    form_version: int
    submitted_at: datetime
    answers: list[AnswerResponse]


class ResponseListResponse(BaseModel):
    items: list[ResponseItem]
    next_cursor: str | None = None


class PublicFormResponse(BaseModel):
    """Form schema exposed to anonymous respondents (no owner/internal fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: PyObjectId
    title: str
    description: str
    version: int
    fields: list[FieldResponse]
