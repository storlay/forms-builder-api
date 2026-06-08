from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from httpx import AsyncClient

from app.core.config import settings
from app.main import create_app


# Tests hit Mongo started via docker compose (docker compose up -d mongo),
# using a separate database that is dropped after each test.
settings.mongo_db = "forms_test"


# noinspection PyUnresolvedReferences
@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    application = create_app()
    async with application.router.lifespan_context(application):
        yield application
        await application.state.client.drop_database(settings.mongo_db)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)  # noqa
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# noinspection PyUnresolvedReferences
@pytest.fixture
def db(app):
    return app.state.db


@pytest.fixture
def make_auth(client):
    async def _make(
        email: str = "owner@example.com", password: str = "supersecret123"
    ) -> dict[str, str]:
        creds = {"email": email, "password": password}
        await client.post("/auth/register", json=creds)
        resp = await client.post("/auth/login", json=creds)
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _make


@pytest.fixture
async def auth_headers(make_auth) -> dict[str, str]:
    return await make_auth()
