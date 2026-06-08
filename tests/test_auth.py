from httpx import AsyncClient


CREDS = {"email": "user@example.com", "password": "supersecret123"}


async def register(client: AsyncClient, **overrides) -> "tuple[int, dict]":
    resp = await client.post("/auth/register", json={**CREDS, **overrides})
    return resp.status_code, resp.json()


async def login(client: AsyncClient, **overrides) -> "tuple[int, dict]":
    resp = await client.post("/auth/login", json={**CREDS, **overrides})
    return resp.status_code, resp.json()


async def test_register_returns_public_user(client: AsyncClient) -> None:
    status_code, body = await register(client)
    assert status_code == 201
    assert body["email"] == CREDS["email"]
    assert isinstance(body["id"], str)
    assert "password_hash" not in body
    assert "password" not in body


async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    await register(client)
    status_code, _ = await register(client)
    assert status_code == 409


async def test_register_normalizes_email(client: AsyncClient) -> None:
    status_code, body = await register(client, email="  USER@Example.com ")
    assert status_code == 201
    assert body["email"] == "user@example.com"


async def test_register_invalid_email_rejected(client: AsyncClient) -> None:
    status_code, _ = await register(client, email="not-an-email")
    assert status_code == 422


async def test_register_short_password_rejected(client: AsyncClient) -> None:
    status_code, _ = await register(client, password="short")
    assert status_code == 422


async def test_login_returns_bearer_token(client: AsyncClient) -> None:
    await register(client)
    status_code, body = await login(client)
    assert status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password_unauthorized(client: AsyncClient) -> None:
    await register(client)
    status_code, _ = await login(client, password="wrongpassword1")
    assert status_code == 401


async def test_login_unknown_email_unauthorized(client: AsyncClient) -> None:
    status_code, _ = await login(client, email="ghost@example.com")
    assert status_code == 401


async def test_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_invalid_token(client: AsyncClient) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


async def test_me_returns_current_user(client: AsyncClient) -> None:
    await register(client)
    _, token_body = await login(client)
    headers = {"Authorization": f"Bearer {token_body['access_token']}"}

    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == CREDS["email"]
