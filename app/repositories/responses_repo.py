from collections.abc import AsyncIterator
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from pymongo import DESCENDING

from app.models.form import FieldType
from app.models.response import DraftResponse
from app.models.response import Response


if TYPE_CHECKING:
    from bson import ObjectId
    from pymongo.asynchronous.database import AsyncDatabase

    from app.models.form import FormField


_HIST_BUCKETS = 5
_CHOICE_TYPES = (FieldType.SINGLE_CHOICE, FieldType.MULTI_CHOICE)
_NUMERIC_TYPES = (FieldType.NUMBER, FieldType.RATING)


def _histogram_boundaries(field: "FormField") -> list[float]:
    """Evenly spaced $bucket boundaries derived from a field's validation range.

    The top boundary is extended by one bucket width so the maximum value is
    included in the last bucket instead of falling into the "out" default.
    """
    v = field.validation
    lo = float(v.min) if v and v.min is not None else 0.0
    default_hi = 10.0 if field.type == FieldType.RATING else 100.0
    hi = float(v.max) if v and v.max is not None else default_hi
    if hi <= lo:
        hi = lo + 1.0
    width = (hi - lo) / _HIST_BUCKETS
    edges = [round(lo + width * i, 4) for i in range(_HIST_BUCKETS)]
    edges.append(round(hi + width, 4))
    return edges


def _build_facets(
    fields: "list[FormField]",
) -> tuple[dict[str, Any], dict[str, list[float]]]:
    """Build one $facet branch per metric so the whole summary runs in a single pass.

    Facet keys are positional (c0, v0, s0, h0, ...) to stay collision-free with
    arbitrary field keys; the boundaries map lets the caller label histograms.
    """
    facets: dict[str, Any] = {
        "_total": [{"$count": "n"}],
        "_timeline": [
            {
                "$group": {
                    "_id": {"$dateTrunc": {"date": "$submitted_at", "unit": "day"}},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ],
    }
    boundaries: dict[str, list[float]] = {}
    for i, field in enumerate(fields):
        base = [{"$unwind": "$answers"}, {"$match": {"answers.key": field.key}}]
        facets[f"c{i}"] = [*base, {"$count": "n"}]
        if field.type in _CHOICE_TYPES:
            stages = list(base)
            if field.type == FieldType.MULTI_CHOICE:
                stages.append({"$unwind": "$answers.value"})
            stages += [
                {"$group": {"_id": "$answers.value", "count": {"$sum": 1}}},
                {"$sort": {"count": -1, "_id": 1}},
            ]
            facets[f"v{i}"] = stages
        elif field.type in _NUMERIC_TYPES:
            facets[f"s{i}"] = [
                *base,
                {
                    "$group": {
                        "_id": None,
                        "avg": {"$avg": "$answers.value"},
                        "min": {"$min": "$answers.value"},
                        "max": {"$max": "$answers.value"},
                    }
                },
            ]
            edges = _histogram_boundaries(field)
            boundaries[field.key] = edges
            facets[f"h{i}"] = [
                *base,
                {
                    "$bucket": {
                        "groupBy": "$answers.value",
                        "boundaries": edges,
                        "default": "out",
                        "output": {"count": {"$sum": 1}},
                    }
                },
            ]
    return facets, boundaries


class ResponsesRepository:
    def __init__(self, db: "AsyncDatabase") -> None:
        self._responses = db.responses
        self._drafts = db.draft_responses

    async def create(
        self,
        *,
        form_id: "ObjectId",
        form_version: int,
        answers: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> Response:
        doc = {
            "form_id": form_id,
            "form_version": form_version,
            "answers": answers,
            "submitted_at": datetime.now(UTC),
            "meta": meta,
        }
        result = await self._responses.insert_one(doc)
        doc["_id"] = result.inserted_id
        return Response.model_validate(doc)

    async def list_by_form(
        self,
        form_id: "ObjectId",
        limit: int,
        cursor: "tuple[datetime, ObjectId] | None",
    ) -> list[Response]:
        """Keyset page of responses, newest first, sorted by (submitted_at, _id).

        The cursor carries both keys so pagination stays correct when several
        responses share a submitted_at; the matching index makes this a range
        scan rather than a $skip over already-seen documents.
        """
        query: dict[str, Any] = {"form_id": form_id}
        if cursor is not None:
            cur_at, cur_id = cursor
            query["$or"] = [
                {"submitted_at": {"$lt": cur_at}},
                {"submitted_at": cur_at, "_id": {"$lt": cur_id}},
            ]
        rows = (
            self._responses.find(query)
            .sort([("submitted_at", DESCENDING), ("_id", DESCENDING)])
            .limit(limit)
        )
        return [Response.model_validate(doc) async for doc in rows]

    async def iter_by_form(self, form_id: "ObjectId") -> AsyncIterator[Response]:
        """Stream every response for a form, newest first, for export.

        Yields documents one at a time so the export endpoint can stream rows
        without buffering the whole result set in memory.
        """
        rows = self._responses.find({"form_id": form_id}).sort(
            [("submitted_at", DESCENDING), ("_id", DESCENDING)]
        )
        async for doc in rows:
            yield Response.model_validate(doc)

    async def create_draft(
        self,
        *,
        form_id: "ObjectId",
        answers: list[dict[str, Any]],
        expires_at: datetime,
    ) -> DraftResponse:
        doc = {"form_id": form_id, "answers": answers, "expires_at": expires_at}
        result = await self._drafts.insert_one(doc)
        doc["_id"] = result.inserted_id
        return DraftResponse.model_validate(doc)

    async def facet_summary(
        self,
        form_id: "ObjectId",
        fields: "list[FormField]",
    ) -> dict[str, Any]:
        """Run the single-pass $facet analytics pipeline for a form.

        Returns the raw facet document plus the histogram boundaries used to
        build it; interpreting them into DTOs is left to the service layer.
        """
        facets, boundaries = _build_facets(fields)
        pipeline = [{"$match": {"form_id": form_id}}, {"$facet": facets}]
        cursor = await self._responses.aggregate(pipeline)
        docs = [doc async for doc in cursor]
        return {"facet": docs[0] if docs else {}, "boundaries": boundaries}
