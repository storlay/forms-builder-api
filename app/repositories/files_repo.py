from typing import TYPE_CHECKING
from typing import Any

from gridfs.asynchronous import AsyncGridFSBucket
from gridfs.errors import NoFile


if TYPE_CHECKING:
    from bson import ObjectId
    from gridfs.asynchronous.grid_file import AsyncGridOut
    from pymongo.asynchronous.database import AsyncDatabase


class FilesRepository:
    def __init__(self, db: "AsyncDatabase") -> None:
        self._bucket = AsyncGridFSBucket(db)

    async def upload(
        self,
        *,
        filename: str,
        source: bytes,
        content_type: str,
        metadata: dict[str, Any],
    ) -> "ObjectId":
        return await self._bucket.upload_from_stream(
            filename, source, metadata={"content_type": content_type, **metadata}
        )

    async def open(self, file_id: "ObjectId") -> "AsyncGridOut | None":
        try:
            return await self._bucket.open_download_stream(file_id)
        except NoFile:
            return None
