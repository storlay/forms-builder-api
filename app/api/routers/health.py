from fastapi import APIRouter

from app.core.db import DbDep


router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: DbDep) -> dict[str, str]:
    await db.command("ping")
    return {"status": "ok"}
