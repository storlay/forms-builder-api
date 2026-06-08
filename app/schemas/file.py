from pydantic import BaseModel

from app.models.py_object_id import PyObjectId


class FileUploadResult(BaseModel):
    file_id: PyObjectId
