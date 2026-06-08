from bson import ObjectId
from httpx import AsyncClient


FILE_FIELDS = [{"key": "doc", "type": "file", "label": "Doc"}]
CONTENT = b"hello, this is a CV file\n" * 100


async def make_form(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    status: str = "published",
    settings=None,
) -> str:
    payload: dict = {"title": "Files form", "fields": FILE_FIELDS}
    if settings is not None:
        payload["settings"] = settings
    resp = await client.post("/forms", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    form_id = resp.json()["id"]
    if status in ("published", "closed"):
        assert (await client.post(f"/forms/{form_id}/publish", headers=headers)).status_code == 200
    if status == "closed":
        assert (await client.post(f"/forms/{form_id}/close", headers=headers)).status_code == 200
    return form_id


async def upload(
    client: AsyncClient,
    form_id: str,
    *,
    content: bytes = CONTENT,
    filename: str = "cv.txt",
    content_type: str = "text/plain",
):
    files = {"file": (filename, content, content_type)}
    return await client.post(f"/f/{form_id}/files", files=files)


async def test_upload_returns_file_id(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    resp = await upload(client, form_id)
    assert resp.status_code == 201, resp.text
    assert ObjectId.is_valid(resp.json()["file_id"])


async def test_download_streams_content(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    file_id = (await upload(client, form_id)).json()["file_id"]
    resp = await client.get(f"/files/{file_id}")
    assert resp.status_code == 200
    assert resp.content == CONTENT
    assert resp.headers["content-type"].startswith("text/plain")
    assert "cv.txt" in resp.headers["content-disposition"]
    assert resp.headers["content-length"] == str(len(CONTENT))


async def test_download_missing_404(client: AsyncClient) -> None:
    assert (await client.get(f"/files/{ObjectId()}")).status_code == 404


async def test_download_invalid_id_404(client: AsyncClient) -> None:
    assert (await client.get("/files/not-an-id")).status_code == 404


async def test_upload_to_draft_404(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers, status="draft")
    assert (await upload(client, form_id)).status_code == 404


async def test_upload_to_missing_404(client: AsyncClient) -> None:
    assert (await upload(client, str(ObjectId()))).status_code == 404


async def test_upload_to_closed_409(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers, status="closed")
    assert (await upload(client, form_id)).status_code == 409


async def test_submit_with_file_enriches_value(
    client: AsyncClient,
    auth_headers,
    db,
) -> None:
    form_id = await make_form(client, auth_headers)
    file_id = (await upload(client, form_id)).json()["file_id"]
    resp = await client.post(
        f"/f/{form_id}/responses",
        json={"answers": {"doc": file_id}},
    )
    assert resp.status_code == 201, resp.text
    doc = await db.responses.find_one({"_id": ObjectId(resp.json()["id"])})
    answer = {a["key"]: a["value"] for a in doc["answers"]}["doc"]
    assert answer["file_id"] == ObjectId(file_id)
    assert answer["filename"] == "cv.txt"
    assert answer["size"] == len(CONTENT)


async def test_submit_with_unknown_file_422(client: AsyncClient, auth_headers) -> None:
    form_id = await make_form(client, auth_headers)
    resp = await client.post(
        f"/f/{form_id}/responses",
        json={"answers": {"doc": str(ObjectId())}},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["errors"]


async def test_submit_with_invalid_file_ref_422(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await make_form(client, auth_headers)
    resp = await client.post(
        f"/f/{form_id}/responses",
        json={"answers": {"doc": "not-an-id"}},
    )
    assert resp.status_code == 422


async def test_submit_rejects_file_from_other_form(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_a = await make_form(client, auth_headers)
    form_b = await make_form(client, auth_headers)
    file_id = (await upload(client, form_a)).json()["file_id"]
    resp = await client.post(
        f"/f/{form_b}/responses",
        json={"answers": {"doc": file_id}},
    )
    assert resp.status_code == 422


async def test_list_responses_serializes_file_answer(
    client: AsyncClient,
    auth_headers,
) -> None:
    form_id = await make_form(client, auth_headers)
    file_id = (await upload(client, form_id)).json()["file_id"]
    await client.post(f"/f/{form_id}/responses", json={"answers": {"doc": file_id}})

    resp = await client.get(f"/forms/{form_id}/responses", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    answer = resp.json()["items"][0]["answers"][0]
    assert answer["key"] == "doc"
    assert answer["value"]["file_id"] == file_id
    assert answer["value"]["filename"] == "cv.txt"
