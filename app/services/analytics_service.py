from typing import TYPE_CHECKING
from typing import Any

from app.core.exceptions import FormNotFound
from app.models.form import FieldType
from app.schemas.analytics import ChoiceCount
from app.schemas.analytics import FieldSummary
from app.schemas.analytics import FormAnalyticsResponse
from app.schemas.analytics import HistogramBucket
from app.schemas.analytics import NumericStats
from app.schemas.analytics import TimelinePoint


if TYPE_CHECKING:
    from bson import ObjectId

    from app.models.form import Form
    from app.models.form import FormField
    from app.repositories.forms_repo import FormsRepository
    from app.repositories.responses_repo import ResponsesRepository


_CHOICE_TYPES = (FieldType.SINGLE_CHOICE, FieldType.MULTI_CHOICE)
_NUMERIC_TYPES = (FieldType.NUMBER, FieldType.RATING)


def _first(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


def _histogram(edges: list[float], rows: list[dict[str, Any]]) -> list[HistogramBucket]:
    """Fill every bucket, including empty ones $bucket omits, by boundary lookup."""
    counts = {row["_id"]: row["count"] for row in rows}
    return [
        HistogramBucket(lower=edges[i], upper=edges[i + 1], count=counts.get(edges[i], 0))
        for i in range(len(edges) - 1)
    ]


def _field_summary(
    field: "FormField",
    facet: dict[str, Any],
    index: int,
    boundaries: dict[str, list[float]],
) -> FieldSummary:
    count_row = _first(facet.get(f"c{index}", []))
    summary = FieldSummary(
        key=field.key,
        type=field.type,
        label=field.label,
        answered=count_row["n"] if count_row else 0,
    )
    if field.type in _CHOICE_TYPES:
        summary.choices = [
            ChoiceCount(value=row["_id"], count=row["count"]) for row in facet.get(f"v{index}", [])
        ]
    elif field.type in _NUMERIC_TYPES:
        stats_row = _first(facet.get(f"s{index}", []))
        summary.stats = NumericStats(**(stats_row or {}))
        summary.histogram = _histogram(
            boundaries[field.key],
            facet.get(f"h{index}", []),
        )
    return summary


def _build_response(
    form: "Form", facet: dict[str, Any], boundaries: dict[str, list[float]]
) -> FormAnalyticsResponse:
    total_row = _first(facet.get("_total", []))
    timeline = [
        TimelinePoint(date=row["_id"].date(), count=row["count"])
        for row in facet.get("_timeline", [])
    ]
    fields = [_field_summary(field, facet, i, boundaries) for i, field in enumerate(form.fields)]
    return FormAnalyticsResponse(
        form_id=form.id,
        total_responses=total_row["n"] if total_row else 0,
        timeline=timeline,
        fields=fields,
    )


class AnalyticsService:
    def __init__(self, forms: "FormsRepository", responses: "ResponsesRepository") -> None:
        self._forms = forms
        self._responses = responses

    async def get_summary(
        self,
        form_id: "ObjectId",
        owner_id: "ObjectId",
    ) -> FormAnalyticsResponse:
        form = await self._forms.get_by_id(form_id)
        # Not-found and not-owned both map to 404 so form existence is not disclosed.
        if form is None or form.owner_id != owner_id:
            raise FormNotFound
        data = await self._responses.facet_summary(form_id, form.fields)
        return _build_response(form, data["facet"], data["boundaries"])
