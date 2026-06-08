from bson import ObjectId
from gridfs.asynchronous.grid_file import AsyncGridOut

from app.core.exceptions import FileNotFound
from app.core.exceptions import FormNotFound
from app.core.exceptions import FormStateError
from app.models.form import FormStatus
from app.repositories.files_repo import FilesRepository
from app.repositories.forms_repo import FormsRepository


class FileService:
    def __init__(self, forms: FormsRepository, files: FilesRepository) -> None:
        self._forms = forms
        self._files = files

    async def upload(
        self,
        form_id: ObjectId,
        *,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> ObjectId:
        form = await self._forms.get_by_id(form_id)
        # Drafts are not publicly visible; treat as not found to avoid disclosure.
        if form is None or form.status == FormStatus.DRAFT:
            raise FormNotFound
        if form.status == FormStatus.CLOSED or not form.settings.accepting_responses:
            raise FormStateError("Form is not accepting responses")
        return await self._files.upload(
            filename=filename,
            source=data,
            content_type=content_type,
            metadata={"form_id": form_id},
        )

    async def open_download(self, file_id: ObjectId) -> AsyncGridOut:
        grid_out = await self._files.open(file_id)
        if grid_out is None:
            raise FileNotFound
        return grid_out
