from typing import TYPE_CHECKING

from pymongo import ASCENDING
from pymongo import DESCENDING


if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


async def ensure_indexes(db: "AsyncDatabase") -> None:
    await db.users.create_index([("email", ASCENDING)], unique=True)

    await db.forms.create_index([("owner_id", ASCENDING), ("status", ASCENDING)])

    await db.form_versions.create_index(
        [("form_id", ASCENDING), ("version", ASCENDING)], unique=True
    )

    await db.responses.create_index(
        [("form_id", ASCENDING), ("submitted_at", DESCENDING), ("_id", DESCENDING)]
    )
    await db.responses.create_index(
        [("form_id", ASCENDING), ("answers.key", ASCENDING)],
    )

    await db.draft_responses.create_index(
        [("expires_at", ASCENDING)],
        expireAfterSeconds=0,
    )
