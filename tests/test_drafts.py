import asyncio
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from bson import ObjectId
from httpx import AsyncClient

from tests.test_responses import make_form
from tests.test_responses import published_form


async def save_draft(client: AsyncClient, form_id: str, answers: dict):
    return await client.post(f"/f/{form_id}/draft", json={"answers": answers})


async def test_draft_accepts_partial_answers(
    client: AsyncClient,
    auth_headers,
    db,
) -> None:
    form_id = await published_form(client, auth_headers)
    # Only one field, required fields omitted — allowed for a draft.
    resp = await save_draft(client, form_id, {"name": "Al"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert ObjectId.is_valid(body["id"])

    doc = await db.draft_responses.find_one({"_id": ObjectId(body["id"])})
    assert {a["key"] for a in doc["answers"]} == {"name"}
    assert doc["expires_at"] > datetime.now(UTC).replace(tzinfo=None)


async def test_draft_rejects_unknown_field(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    resp = await save_draft(client, form_id, {"unknown": "x"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["errors"]


async def test_draft_validates_provided_value(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await published_form(client, auth_headers)
    # age is optional, but a provided value must still satisfy its constraints.
    resp = await save_draft(client, form_id, {"age": 200})
    assert resp.status_code == 422, resp.text


async def test_draft_to_draft_form_404(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    assert (await save_draft(client, form_id, {"name": "Al"})).status_code == 404


async def test_draft_to_closed_409(client: AsyncClient, auth_headers) -> None:
    form_id = await published_form(client, auth_headers)
    await client.post(f"/forms/{form_id}/close", headers=auth_headers)
    assert (await save_draft(client, form_id, {"name": "Al"})).status_code == 409


async def test_ttl_index_deletes_expired_draft(
    client: AsyncClient,
    auth_headers,
    db,
    app,
) -> None:
    form_id = await published_form(client, auth_headers)
    body = (await save_draft(client, form_id, {"name": "Al"})).json()
    draft_id = ObjectId(body["id"])

    # Force the draft to be already expired.
    past = datetime.now(UTC) - timedelta(seconds=60)
    await db.draft_responses.update_one(
        {"_id": draft_id},
        {"$set": {"expires_at": past}},
    )

    # Speed up Mongo's TTL monitor (default 60s) so the test stays fast.
    admin = app.state.client.admin
    await admin.command("setParameter", 1, ttlMonitorSleepSecs=1)
    try:
        for _ in range(30):
            if await db.draft_responses.find_one({"_id": draft_id}) is None:
                break
            await asyncio.sleep(1)
        assert await db.draft_responses.find_one({"_id": draft_id}) is None
    finally:
        await admin.command("setParameter", 1, ttlMonitorSleepSecs=60)
