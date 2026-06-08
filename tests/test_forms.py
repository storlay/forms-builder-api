from bson import ObjectId
from httpx import AsyncClient


FORM = {
    "title": "NPS",
    "description": "survey",
    "fields": [
        {
            "key": "q1",
            "type": "single_choice",
            "label": "Rate",
            "required": True,
            "options": ["bad", "ok", "great"],
        },
        {"key": "q2", "type": "number", "label": "Score", "validation": {"min": 0, "max": 10}},
    ],
}


async def create_form(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    resp = await client.post("/forms", json={**FORM, **overrides}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_form_starts_as_draft_v1(
    client: AsyncClient,
    auth_headers,
) -> None:
    body = await create_form(client, auth_headers)
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert isinstance(body["id"], str)
    assert body["published_at"] is None
    assert [f["order"] for f in body["fields"]] == [0, 1]


async def test_create_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/forms", json=FORM)
    assert resp.status_code == 401


async def test_get_own_form(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    resp = await client.get(f"/forms/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_missing_form_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get(f"/forms/{ObjectId()}", headers=auth_headers)
    assert resp.status_code == 404


async def test_get_invalid_id_404(client: AsyncClient, auth_headers) -> None:
    resp = await client.get("/forms/not-an-id", headers=auth_headers)
    assert resp.status_code == 404


async def test_other_user_cannot_access_form(client: AsyncClient, make_auth) -> None:
    owner = await make_auth("a@example.com")
    intruder = await make_auth("b@example.com")
    created = await create_form(client, owner)

    assert (await client.get(f"/forms/{created['id']}", headers=intruder)).status_code == 404
    assert (
        await client.patch(
            f"/forms/{created['id']}",
            json={"title": "x"},
            headers=intruder,
        )
    ).status_code == 404
    assert (
        await client.post(f"/forms/{created['id']}/publish", headers=intruder)
    ).status_code == 404
    assert (await client.delete(f"/forms/{created['id']}", headers=intruder)).status_code == 404


async def test_list_returns_only_own_forms(client: AsyncClient, make_auth) -> None:
    owner = await make_auth("a@example.com")
    other = await make_auth("b@example.com")
    await create_form(client, owner, title="mine")
    await create_form(client, other, title="theirs")

    resp = await client.get("/forms", headers=owner)
    assert resp.status_code == 200
    body = resp.json()
    titles = [f["title"] for f in body["items"]]
    assert titles == ["mine"]


async def test_list_keyset_pagination(client: AsyncClient, auth_headers) -> None:
    for i in range(3):
        await create_form(client, auth_headers, title=f"f{i}")

    first = (await client.get("/forms?limit=2", headers=auth_headers)).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = (
        await client.get(
            f"/forms?limit=2&cursor={first['next_cursor']}",
            headers=auth_headers,
        )
    ).json()
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


async def test_patch_draft_edits_in_place_without_bump(
    client: AsyncClient,
    auth_headers,
) -> None:
    created = await create_form(client, auth_headers)
    new_fields = [{"key": "only", "type": "short_text", "label": "Name"}]
    resp = await client.patch(
        f"/forms/{created['id']}",
        json={"title": "renamed", "fields": new_fields},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "renamed"
    assert body["version"] == 1
    assert [f["key"] for f in body["fields"]] == ["only"]


async def test_publish_creates_snapshot_and_sets_status(
    client: AsyncClient, auth_headers, db
) -> None:
    created = await create_form(client, auth_headers)
    resp = await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    assert body["version"] == 1
    assert body["published_at"] is not None

    count = await db.form_versions.count_documents({"form_id": ObjectId(created["id"])})
    assert count == 1


async def test_publish_empty_form_rejected(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers, fields=[])
    resp = await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    assert resp.status_code == 409


async def test_publish_twice_rejected(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    resp = await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    assert resp.status_code == 409


async def test_published_schema_edit_bumps_version_and_snapshot(
    client: AsyncClient, auth_headers, db
) -> None:
    created = await create_form(client, auth_headers)
    await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)

    new_fields = [{"key": "q1", "type": "short_text", "label": "Comment"}]
    resp = await client.patch(
        f"/forms/{created['id']}", json={"fields": new_fields}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 2
    assert [f["key"] for f in body["fields"]] == ["q1"]

    versions = await db.form_versions.count_documents(
        {"form_id": ObjectId(created["id"])},
    )
    assert versions == 2


async def test_published_metadata_edit_keeps_version(
    client: AsyncClient,
    auth_headers,
) -> None:
    created = await create_form(client, auth_headers)
    await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)

    resp = await client.patch(
        f"/forms/{created['id']}", json={"title": "new title"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "new title"
    assert body["version"] == 1


async def test_close_published_form(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    resp = await client.post(f"/forms/{created['id']}/close", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


async def test_close_draft_rejected(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    resp = await client.post(f"/forms/{created['id']}/close", headers=auth_headers)
    assert resp.status_code == 409


async def test_closed_form_cannot_be_edited(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    await client.post(f"/forms/{created['id']}/publish", headers=auth_headers)
    await client.post(f"/forms/{created['id']}/close", headers=auth_headers)
    resp = await client.patch(
        f"/forms/{created['id']}",
        json={"title": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


async def test_delete_form(client: AsyncClient, auth_headers) -> None:
    created = await create_form(client, auth_headers)
    resp = await client.delete(f"/forms/{created['id']}", headers=auth_headers)
    assert resp.status_code == 204
    assert (await client.get(f"/forms/{created['id']}", headers=auth_headers)).status_code == 404


async def test_choice_field_requires_options(client: AsyncClient, auth_headers) -> None:
    bad = [{"key": "q1", "type": "single_choice", "label": "Pick"}]
    resp = await client.post(
        "/forms",
        json={**FORM, "fields": bad},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_non_choice_field_rejects_options(
    client: AsyncClient,
    auth_headers,
) -> None:
    bad = [{"key": "q1", "type": "short_text", "label": "Name", "options": ["x"]}]
    resp = await client.post(
        "/forms",
        json={**FORM, "fields": bad},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_duplicate_field_keys_rejected(client: AsyncClient, auth_headers) -> None:
    dup = [
        {"key": "q1", "type": "short_text", "label": "A"},
        {"key": "q1", "type": "short_text", "label": "B"},
    ]
    resp = await client.post(
        "/forms",
        json={**FORM, "fields": dup},
        headers=auth_headers,
    )
    assert resp.status_code == 422
