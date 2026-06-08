from datetime import datetime
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.models.py_object_id import PyObjectId


class Answer(BaseModel):
    key: str
    value: Any


class Response(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    form_id: PyObjectId
    form_version: int
    answers: list[Answer]
    submitted_at: datetime
    meta: dict[str, Any] = Field(default_factory=dict)


class DraftResponse(BaseModel):
    """Partial, unsubmitted answer. Removed by a TTL index after expires_at."""

    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    form_id: PyObjectId
    answers: list[Answer]
    expires_at: datetime
