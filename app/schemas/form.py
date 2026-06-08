from datetime import datetime

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from app.models.form import FieldType
from app.models.form import FieldValidation
from app.models.form import FormSettings
from app.models.form import FormStatus
from app.models.py_object_id import PyObjectId


_CHOICE_TYPES = {FieldType.SINGLE_CHOICE, FieldType.MULTI_CHOICE}


class FieldRequest(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_]+$")
    type: FieldType
    label: str = Field(min_length=1, max_length=200)
    required: bool = False
    options: list[str] | None = None
    validation: FieldValidation | None = None

    @model_validator(mode="after")
    def check_options(self) -> "FieldRequest":
        if self.type in _CHOICE_TYPES:
            if not self.options:
                raise ValueError(f"{self.type} requires non-empty options")
        elif self.options is not None:
            raise ValueError(f"{self.type} must not have options")
        return self


def _ensure_unique_keys(fields: list[FieldRequest]) -> None:
    keys = [f.key for f in fields]
    if len(keys) != len(set(keys)):
        raise ValueError("Field keys must be unique")


class FormCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    fields: list[FieldRequest] = Field(default_factory=list)
    settings: FormSettings = Field(default_factory=FormSettings)

    @model_validator(mode="after")
    def unique_keys(self) -> "FormCreateRequest":
        _ensure_unique_keys(self.fields)
        return self


class FormUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    fields: list[FieldRequest] | None = None
    settings: FormSettings | None = None

    @model_validator(mode="after")
    def unique_keys(self) -> "FormUpdateRequest":
        if self.fields is not None:
            _ensure_unique_keys(self.fields)
        return self


class FieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    type: FieldType
    label: str
    required: bool
    order: int
    options: list[str] | None = None
    validation: FieldValidation | None = None


class FormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PyObjectId
    owner_id: PyObjectId
    title: str
    description: str
    status: FormStatus
    version: int
    fields: list[FieldResponse]
    settings: FormSettings
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class FormListResponse(BaseModel):
    items: list[FormResponse]
    next_cursor: str | None = None
