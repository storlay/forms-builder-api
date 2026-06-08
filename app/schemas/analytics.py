from datetime import date

from pydantic import BaseModel

from app.models.form import FieldType
from app.models.py_object_id import PyObjectId


class ChoiceCount(BaseModel):
    value: str
    count: int


class NumericStats(BaseModel):
    avg: float | None = None
    min: float | None = None
    max: float | None = None


class HistogramBucket(BaseModel):
    lower: float
    upper: float
    count: int


class FieldSummary(BaseModel):
    key: str
    type: FieldType
    label: str
    answered: int
    choices: list[ChoiceCount] | None = None
    stats: NumericStats | None = None
    histogram: list[HistogramBucket] | None = None


class TimelinePoint(BaseModel):
    date: date
    count: int


class FormAnalyticsResponse(BaseModel):
    form_id: PyObjectId
    total_responses: int
    timeline: list[TimelinePoint]
    fields: list[FieldSummary]
