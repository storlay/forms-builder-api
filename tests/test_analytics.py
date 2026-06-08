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
    {"key": "score", "type": "rating", "label": "Score", "validation": {"min": 1, "max": 5}},
    {"key": "bio", "type": "long_text", "label": "Bio"},
]

# color (red x2, green x2); tags a:2 b:2 c:1 (answered 3);
# age 10/50/90 (answered 3); score 5/3/5/1 (answered 4); bio answered 2.
SUBMISSIONS = [
    {"color": "red", "tags": ["a", "b"], "age": 10, "score": 5, "bio": "x"},
    {"color": "red", "tags": ["b"], "age": 50, "score": 3},
    {"color": "green", "tags": ["a", "c"], "age": 90, "score": 5, "bio": "y"},
    {"color": "green", "score": 1},
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


async def analytics(client: AsyncClient, form_id: str, headers: dict[str, str]) -> dict:
    resp = await client.get(f"/forms/{form_id}/analytics", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body["by_key"] = {f["key"]: f for f in body["fields"]}
    return body


async def test_total_and_timeline(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    body = await analytics(client, form_id, auth_headers)
    assert body["total_responses"] == 4
    assert sum(p["count"] for p in body["timeline"]) == 4
    assert all("date" in p for p in body["timeline"])


async def test_single_choice_counts(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    color = (await analytics(client, form_id, auth_headers))["by_key"]["color"]
    assert color["answered"] == 4
    assert {c["value"]: c["count"] for c in color["choices"]} == {"red": 2, "green": 2}


async def test_multi_choice_counts(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    tags = (await analytics(client, form_id, auth_headers))["by_key"]["tags"]
    assert tags["answered"] == 3
    assert {c["value"]: c["count"] for c in tags["choices"]} == {"a": 2, "b": 2, "c": 1}


async def test_number_stats_and_histogram(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    age = (await analytics(client, form_id, auth_headers))["by_key"]["age"]
    assert age["answered"] == 3
    assert age["stats"] == {"avg": 50.0, "min": 10.0, "max": 90.0}
    assert [b["count"] for b in age["histogram"]] == [1, 0, 1, 0, 1]


async def test_rating_stats_and_histogram(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    score = (await analytics(client, form_id, auth_headers))["by_key"]["score"]
    assert score["answered"] == 4
    assert score["stats"] == {"avg": 3.5, "min": 1.0, "max": 5.0}
    assert [b["count"] for b in score["histogram"]] == [1, 0, 1, 0, 2]


async def test_text_only_answered_count(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await seed(client, form_id)
    bio = (await analytics(client, form_id, auth_headers))["by_key"]["bio"]
    assert bio["answered"] == 2
    assert bio["choices"] is None
    assert bio["stats"] is None


async def test_no_responses_zeroed(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    body = await analytics(client, form_id, auth_headers)
    assert body["total_responses"] == 0
    assert body["timeline"] == []
    assert body["by_key"]["color"]["answered"] == 0
    assert body["by_key"]["color"]["choices"] == []
    assert body["by_key"]["age"]["stats"] == {"avg": None, "min": None, "max": None}
    assert [b["count"] for b in body["by_key"]["age"]["histogram"]] == [0, 0, 0, 0, 0]


async def test_analytics_requires_auth(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    assert (await client.get(f"/forms/{form_id}/analytics")).status_code == 401


async def test_analytics_other_owner_404(
    client: AsyncClient,
    auth_headers,
    make_auth,
) -> None:
    form_id = await published_form(client, auth_headers)
    other = await make_auth(email="intruder@example.com")
    assert (await client.get(f"/forms/{form_id}/analytics", headers=other)).status_code == 404


async def test_analytics_missing_form_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get(f"/forms/{ObjectId()}/analytics", headers=auth_headers)
    assert resp.status_code == 404
