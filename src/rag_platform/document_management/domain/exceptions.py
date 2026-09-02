"""DocumentManagement-specific exceptions."""

from __future__ import annotations

from rag_platform.core.exceptions import NotFoundError, ValidationError


class DocumentNotFoundError(NotFoundError):
    message = "Document not found."
    error_type = "document-not-found"


class FileTooLargeError(ValidationError):
    message = "The uploaded file exceeds the maximum allowed size."
    error_type = "file-too-large"


class UnsupportedContentTypeError(ValidationError):
    message = "The uploaded file's content type is not supported."
    error_type = "unsupported-content-type"


class EmptyFileError(ValidationError):
    message = "The uploaded file is empty."
    error_type = "empty-file"
