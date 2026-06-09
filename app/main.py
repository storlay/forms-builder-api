from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from pymongo import AsyncMongoClient

from app.api.routers import analytics
from app.api.routers import auth
from app.api.routers import files
from app.api.routers import forms
from app.api.routers import health
from app.api.routers import responses
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.indexes import ensure_indexes


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    content = {"detail": exc.detail}
    errors = getattr(exc, "errors", None)
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(status_code=exc.status_code, content=content)


# noinspection PyUnresolvedReferences
@asynccontextmanager
async def lifespan(_app: FastAPI):
    client: AsyncMongoClient = AsyncMongoClient(settings.mongo_uri)
    _app.state.client = client
    _app.state.db = client[settings.mongo_db]
    _app.state.public_limiter = SlidingWindowRateLimiter(
        settings.public_rate_limit,
        settings.public_rate_window_seconds,
    )
    await ensure_indexes(_app.state.db)
    yield
    await client.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Forms Constructor", lifespan=lifespan)
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(forms.router)
    app.include_router(responses.router)
    app.include_router(files.router)
    app.include_router(analytics.router)
    return app


app = create_app()
