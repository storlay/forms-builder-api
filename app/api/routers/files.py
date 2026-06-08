from fastapi import APIRouter
from fastapi import UploadFile
from fastapi import status
from fastapi.responses import StreamingResponse

from app.api.deps import FileId
from app.api.deps import FileServiceDep
from app.api.deps import FormId
from app.schemas.file import FileUploadResult


router = APIRouter(tags=["files"])


@router.post(
    "/f/{form_id}/files",
    response_model=FileUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    form_id: FormId,
    file: UploadFile,
    service: FileServiceDep,
) -> FileUploadResult:
    file_id = await service.upload(
        form_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        data=await file.read(),
    )
    return FileUploadResult(file_id=file_id)


@router.get("/files/{file_id}")
async def download_file(
    file_id: FileId,
    service: FileServiceDep,
) -> StreamingResponse:
    grid_out = await service.open_download(file_id)
    content_type = (grid_out.metadata or {}).get(
        "content_type",
        "application/octet-stream",
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{grid_out.filename}"',
        "Content-Length": str(grid_out.length),
    }
    # AsyncGridOut is an async iterator of chunks -> streamed without buffering in memory.
    return StreamingResponse(
        grid_out,
        media_type=content_type,
        headers=headers,
    )
