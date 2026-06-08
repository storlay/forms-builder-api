from typing import Any

from fastapi import status


class AppError(Exception):
    """Base domain error. Mapped to HTTP in a single handler."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = "Application error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class EmailAlreadyExists(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Email already registered"


class InvalidCredentials(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Incorrect email or password"


class FormNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Form not found"


class FormStateError(AppError):
    status_code = status.HTTP_409_CONFLICT
    detail = "Invalid form state for this operation"


class FileNotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "File not found"


class ResponseValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Response validation failed"

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        super().__init__()
