import pytest
from bson import ObjectId
from httpx import AsyncClient


ALL_FIELDS = [
    {
        "key": "name",
        "type": "short_text",
        "label": "Name",
        "required": True,
        "validation": {"max_length": 10},
    },
    {"key": "bio", "type": "long_text", "label": "Bio"},
    {"key": "mail", "type": "email", "label": "Email", "required": True},
    {"key": "age", "type": "number", "label": "Age", "validation": {"min": 0, "max": 120}},
    {"key": "born", "type": "date", "label": "Born"},
    {
        "key": "color",
        "type": "single_choice",
        "label": "Color",
        "required": True,
        "options": ["red", "green"],
    },
    {"key": "tags", "type": "multi_choice", "label": "Tags", "options": ["a", "b", "c"]},
    {"key": "score", "type": "rating", "label": "Score", "validation": {"min": 1, "max": 5}},
    {"key": "cv", "type": "file", "label": "CV"},
]

VALID = {
    "name": "Alice",
    "bio": "hello",
    "mail": "a@b.com",
    "age": 30,
    "born": "2000-01-01",
    "color": "red",
    "tags": ["a", "b"],
    "score": 4,
}

REQUIRED_ONLY = {"name": "Bob", "mail": "b@c.com", "color": "green"}


async def make_form(
    client: AsyncClient, headers: dict[str, str], *, fields=None, settings=None
) -> str:
    payload = {"title": "All types", "fields": fields if fields is not None else ALL_FIELDS}
    if settings is not None:
        payload["settings"] = settings
    resp = await client.post("/forms", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def published_form(client: AsyncClient, headers: dict[str, str], **kwargs) -> str:
    form_id = await make_form(client, headers, **kwargs)
    resp = await client.post(f"/forms/{form_id}/publish", headers=headers)
    assert resp.status_code == 200, resp.text
    return form_id


async def submit(client: AsyncClient, form_id: str, answers: dict):
    return await client.post(f"/f/{form_id}/responses", json={"answers": answers})


async def test_public_form_hides_owner(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await client.get(f"/f/{form_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "owner_id" not in body
    assert {f["key"] for f in body["fields"]} == {f["key"] for f in ALL_FIELDS}


async def test_public_form_draft_not_visible(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    assert (await client.get(f"/f/{form_id}")).status_code == 404


async def test_submit_valid_all_types_anonymous(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await submit(client, form_id, VALID)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["form_version"] == 1
    assert ObjectId.is_valid(body["id"])


async def test_submit_persists_answers(client: AsyncClient, auth_headers, db) -> None:
    form_id = await published_form(client, auth_headers)
    body = (await submit(client, form_id, VALID)).json()
    doc = await db.responses.find_one({"_id": ObjectId(body["id"])})
    assert doc["form_version"] == 1
    stored = {a["key"]: a["value"] for a in doc["answers"]}
    assert stored["age"] == 30
    assert stored["tags"] == ["a", "b"]
    assert "ip_hash" in doc["meta"]


async def test_optional_fields_can_be_omitted(
    client: AsyncClient,
    auth_headers,
    db,
) -> None:
    form_id = await published_form(client, auth_headers)
    body = (await submit(client, form_id, REQUIRED_ONLY)).json()
    doc = await db.responses.find_one({"_id": ObjectId(body["id"])})
    keys = {a["key"] for a in doc["answers"]}
    assert keys == {"name", "mail", "color"}


@pytest.mark.parametrize(
    "patch",
    [
        pytest.param({"name": None}, id="missing-required-text"),
        pytest.param({"color": None}, id="missing-required-choice"),
        pytest.param({"unknown": "x"}, id="unknown-field"),
        pytest.param({"name": "way-too-long-name"}, id="text-too-long"),
        pytest.param({"mail": "not-an-email"}, id="bad-email"),
        pytest.param({"age": 200}, id="number-above-max"),
        pytest.param({"age": "abc"}, id="number-not-a-number"),
        pytest.param({"score": 9}, id="rating-out-of-range"),
        pytest.param({"born": "not-a-date"}, id="bad-date"),
        pytest.param({"color": "purple"}, id="single-choice-bad-option"),
        pytest.param({"tags": ["a", "z"]}, id="multi-choice-bad-option"),
    ],
)
async def test_submit_invalid_returns_422(
    client: AsyncClient,
    auth_headers,
    patch,
) -> None:
    form_id = await published_form(client, auth_headers)
    answers = {**VALID, **patch}
    answers = {k: v for k, v in answers.items() if v is not None}
    resp = await submit(client, form_id, answers)
    assert resp.status_code == 422, resp.text
    assert resp.json()["errors"]


async def test_submit_to_draft_404(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    assert (await submit(client, form_id, VALID)).status_code == 404


async def test_submit_to_missing_404(client: AsyncClient) -> None:
    assert (await submit(client, str(ObjectId()), VALID)).status_code == 404


async def test_submit_to_closed_409(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await client.post(f"/forms/{form_id}/close", headers=auth_headers)
    assert (await submit(client, form_id, VALID)).status_code == 409


async def test_submit_when_not_accepting_409(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(
        client,
        auth_headers,
        settings={"accepting_responses": False},
    )
    assert (await submit(client, form_id, VALID)).status_code == 409


async def _submit_n(client: AsyncClient, form_id: str, n: int) -> list[str]:
    """Submit n responses; return their ids in submission order (oldest first)."""
    ids = []
    for i in range(n):
        body = (await submit(client, form_id, {**REQUIRED_ONLY, "name": f"u{i}"})).json()
        ids.append(body["id"])
    return ids


async def _page(client, form_id, headers, *, limit, cursor=None):
    params = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    resp = await client.get(
        f"/forms/{form_id}/responses",
        params=params,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_responses_listed_newest_first(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    ids = await _submit_n(client, form_id, 3)
    page = await _page(client, form_id, auth_headers, limit=20)
    assert [item["id"] for item in page["items"]] == list(reversed(ids))
    assert page["next_cursor"] is None


async def test_keyset_pages_cover_all_without_duplicates(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    ids = await _submit_n(client, form_id, 5)

    collected: list[str] = []
    cursor = None
    while True:
        page = await _page(client, form_id, auth_headers, limit=2, cursor=cursor)
        collected.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert collected == list(reversed(ids))
    assert len(set(collected)) == 5


async def test_cursor_is_stable_under_inserts(
    client: AsyncClient,
    auth_headers,
) -> None:
    """A response inserted after the first page must not shift or duplicate
    already-seen rows — the keyset cursor pins position, unlike offset/skip."""
    form_id = await published_form(client, auth_headers)
    ids = await _submit_n(client, form_id, 4)  # oldest -> newest

    page1 = await _page(client, form_id, auth_headers, limit=2)
    assert [i["id"] for i in page1["items"]] == [ids[3], ids[2]]

    # Insert a brand-new (newest) response between the two reads.
    newest = (await submit(client, form_id, {**REQUIRED_ONLY, "name": "late"})).json()["id"]

    page2 = await _page(
        client,
        form_id,
        auth_headers,
        limit=2,
        cursor=page1["next_cursor"],
    )
    page2_ids = [i["id"] for i in page2["items"]]

    assert page2_ids == [ids[1], ids[0]]  # no skip, no duplicate of page1's tail
    assert newest not in page2_ids


async def test_empty_form_returns_no_items(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    page = await _page(client, form_id, auth_headers, limit=20)
    assert page == {"items": [], "next_cursor": None}


async def test_malformed_cursor_pages_from_start(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    ids = await _submit_n(client, form_id, 2)
    page = await _page(client, form_id, auth_headers, limit=20, cursor="not-a-cursor")
    assert [i["id"] for i in page["items"]] == list(reversed(ids))


async def test_list_responses_requires_auth(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    assert (await client.get(f"/forms/{form_id}/responses")).status_code == 401


async def test_list_responses_other_owner_404(
    client: AsyncClient,
    auth_headers,
    make_auth,
) -> None:
    form_id = await published_form(client, auth_headers)
    other = await make_auth(email="intruder@example.com")
    resp = await client.get(f"/forms/{form_id}/responses", headers=other)
    assert resp.status_code == 404
