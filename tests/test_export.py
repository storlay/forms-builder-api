import csv
import io
import json

from bson import ObjectId
from httpx import AsyncClient


FIELDS = [
    {
        "key": "color",
        "type": "single_choice",
        "label": "Color",
        "required": True,
        "options": ["red", "green", "blue"],
    },
    {"key": "tags", "type": "multi_choice", "label": "Tags", "options": ["a", "b", "c"]},
    {"key": "age", "type": "number", "label": "Age", "validation": {"min": 0, "max": 100}},
    {"key": "bio", "type": "long_text", "label": "Bio"},
]

SUBMISSIONS = [
    {"color": "red", "tags": ["a", "b"], "age": 10, "bio": "hello"},
    {"color": "green", "age": 50},
]


async def published_form(
    client: AsyncClient,
    headers: dict[str, str],
    fields=FIELDS,
) -> str:
    resp = await client.post(
        "/forms",
        json={"title": "Survey", "fields": fields},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    form_id = resp.json()["id"]
    resp = await client.post(f"/forms/{form_id}/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    return form_id


async def seed(client: AsyncClient, form_id: str) -> None:
    for answers in SUBMISSIONS:
        resp = await client.post(f"/f/{form_id}/responses", json={"answers": answers})
        assert resp.status_code == 201, resp.text


async def test_csv_export_matches_responses(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)

    resp = await client.get(
        f"/forms/{form_id}/export", params={"format": "csv"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 2
    assert list(rows[0].keys()) == ["id", "submitted_at", "color", "tags", "age", "bio"]

    by_color = {r["color"]: r for r in rows}
    assert by_color["red"]["age"] == "10"
    assert by_color["red"]["bio"] == "hello"
    assert json.loads(by_color["red"]["tags"]) == ["a", "b"]
    # Omitted optional answers render as empty cells.
    assert by_color["green"]["tags"] == ""
    assert by_color["green"]["bio"] == ""


async def test_csv_is_default_format(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    resp = await client.get(f"/forms/{form_id}/export", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


async def test_csv_export_empty_form_header_only(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await client.get(
        f"/forms/{form_id}/export", params={"format": "csv"}, headers=auth_headers
    )
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert rows == [["id", "submitted_at", "color", "tags", "age", "bio"]]


async def test_json_export_matches_responses(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)

    resp = await client.get(
        f"/forms/{form_id}/export", params={"format": "json"}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json")

    items = json.loads(resp.text)
    assert len(items) == 2
    by_color = {item["answers"]["color"]: item for item in items}
    assert by_color["red"]["answers"] == {
        "color": "red",
        "tags": ["a", "b"],
        "age": 10,
        "bio": "hello",
    }
    assert by_color["green"]["answers"] == {"color": "green", "age": 50}
    assert all(ObjectId.is_valid(item["id"]) for item in items)
    assert all(item["form_version"] == 1 for item in items)


async def test_json_export_empty_form_empty_array(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await client.get(
        f"/forms/{form_id}/export", params={"format": "json"}, headers=auth_headers
    )
    assert json.loads(resp.text) == []


async def test_invalid_format_422(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await client.get(
        f"/forms/{form_id}/export", params={"format": "xml"}, headers=auth_headers
    )
    assert resp.status_code == 422


async def test_export_requires_auth(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    assert (await client.get(f"/forms/{form_id}/export")).status_code == 401


async def test_export_other_owner_404(
    client: AsyncClient,
    auth_headers,
    make_auth,
) -> None:
    form_id = await published_form(client, auth_headers)
    other = await make_auth(email="intruder@example.com")
    assert (await client.get(f"/forms/{form_id}/export", headers=other)).status_code == 404


async def test_export_missing_form_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get(f"/forms/{ObjectId()}/export", headers=auth_headers)
    assert resp.status_code == 404
