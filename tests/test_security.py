from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import SlidingWindowRateLimiter


FORM = {
    "title": "Survey",
    "fields": [{"key": "name", "type": "short_text", "label": "Name", "required": True}],
}
FILE_FORM = {
    "title": "Files",
    "fields": [{"key": "doc", "type": "file", "label": "Doc"}],
}


async def published(client: AsyncClient, headers: dict[str, str], payload: dict = FORM) -> str:
    form_id = (await client.post("/forms", json=payload, headers=headers)).json()["id"]
    assert (await client.post(f"/forms/{form_id}/publish", headers=headers)).status_code == 200
    return form_id


async def test_public_submit_is_rate_limited(app, client: AsyncClient, auth_headers) -> None:
    app.state.public_limiter = SlidingWindowRateLimiter(limit=3, window_seconds=60)
    form_id = await published(client, auth_headers)
    body = {"answers": {"name": "x"}}

    for _ in range(3):
        assert (await client.post(f"/f/{form_id}/responses", json=body)).status_code == 201
    blocked = await client.post(f"/f/{form_id}/responses", json=body)
    assert blocked.status_code == 429


async def test_submit_and_draft_share_one_budget(app, client: AsyncClient, auth_headers) -> None:
    app.state.public_limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    form_id = await published(client, auth_headers)
    body = {"answers": {"name": "x"}}

    assert (await client.post(f"/f/{form_id}/responses", json=body)).status_code == 201
    assert (await client.post(f"/f/{form_id}/draft", json=body)).status_code == 201
    blocked = await client.post(f"/f/{form_id}/draft", json=body)
    assert blocked.status_code == 429


async def test_owner_endpoints_are_not_rate_limited(app, client: AsyncClient, auth_headers) -> None:
    app.state.public_limiter = SlidingWindowRateLimiter(limit=1, window_seconds=60)
    for _ in range(5):
        assert (await client.get("/forms", headers=auth_headers)).status_code == 200


async def test_upload_too_large_rejected(client: AsyncClient, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 128)
    form_id = await published(client, auth_headers, FILE_FORM)
    files = {"file": ("big.bin", b"a" * 256, "application/octet-stream")}
    resp = await client.post(f"/f/{form_id}/files", files=files)
    assert resp.status_code == 413


async def test_upload_within_limit_ok(client: AsyncClient, auth_headers, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_upload_bytes", 1024)
    form_id = await published(client, auth_headers, FILE_FORM)
    files = {"file": ("ok.bin", b"a" * 256, "application/octet-stream")}
    resp = await client.post(f"/f/{form_id}/files", files=files)
    assert resp.status_code == 201
