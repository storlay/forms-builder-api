from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field

from app.models.py_object_id import PyObjectId


class FieldType(StrEnum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    EMAIL = "email"
    NUMBER = "number"
    DATE = "date"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    RATING = "rating"
    FILE = "file"


class FormStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class FieldValidation(BaseModel):
    min: float | None = None
    max: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    regex: str | None = None


class FormField(BaseModel):
    key: str
    type: FieldType
    label: str
    required: bool = False
    order: int = 0
    options: list[str] | None = None
    validation: FieldValidation | None = None


class FormSettings(BaseModel):
    accepting_responses: bool = True
    response_limit: int | None = None
    max_file_size_bytes: int | None = Field(default=None, gt=0)
    allowed_file_types: list[str] | None = None


class Form(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    owner_id: PyObjectId
    title: str
    description: str = ""
    status: FormStatus
    version: int
    fields: list[FormField]
    settings: FormSettings
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class FormVersion(BaseModel):
    """Immutable snapshot of a form's fields at a given version."""

    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId = Field(alias="_id")
    form_id: PyObjectId
    version: int
    fields: list[FormField]
    created_at: datetime
